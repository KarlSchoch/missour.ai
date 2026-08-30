from datetime import datetime, timezone
from decimal import Decimal
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from transcription.models import ModelPrice, Summary, TaskPricing, Transcript, UsageEvent
from transcription.services.pricing import PricingResolutionError
from transcription.summary.summary_manager import SummaryManager


class SummaryManagerSummarizeTests(TestCase):
    model_name = "summary-manager-test-model"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="summary-manager-user")
        cls.transcript = Transcript.objects.create(
            name="Summary manager transcript",
            transcript_text="A lengthy hearing transcript.",
            created_by=cls.user,
        )

    def setUp(self):
        super().setUp()
        self.model_price = ModelPrice.objects.create(
            provider=ModelPrice.Provider.OPENAI,
            model_name=self.model_name,
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            input_rate_per_million=Decimal("1.25"),
            cached_input_rate_per_million=Decimal("0.25"),
            output_rate_per_million=Decimal("5.00"),
            currency="USD",
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        self.task_pricing = TaskPricing.objects.create(
            task_type=TaskPricing.TaskType.SUMMARY,
            model_price=self.model_price,
            multiplier=Decimal("1.5"),
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

    def response(self):
        return SimpleNamespace(
            id="summary-request-123",
            content="A concise hearing summary.",
            usage_metadata={
                "input_tokens": 2_000_000,
                "output_tokens": 1_000_000,
                "input_token_details": {"cache_read": 500_000},
            },
            response_metadata={},
        )

    def manager(self, llm=None, *, model_name=None, provider="openai"):
        llm = llm or Mock()
        with patch(
            "transcription.summary.summary_manager.init_chat_model",
            return_value=llm,
        ):
            manager = SummaryManager(
                api_key="test-key",
                summary_model=model_name or self.model_name,
                model_provider=provider,
            )
        return manager

    def test_summarize_creates_summary_and_completed_usage_event(self):
        llm = Mock()
        llm.invoke.return_value = self.response()

        summary = self.manager(llm).summarize(
            self.transcript.transcript_text,
            self.transcript,
            operation_id="happy-path",
        )

        self.assertEqual(Summary.objects.count(), 1)
        self.assertEqual(summary.text, "A concise hearing summary.")
        self.assertEqual(summary.summary_type, Summary.SummaryType.GENERAL)
        event = UsageEvent.objects.get()
        self.assertEqual(event.status, UsageEvent.Status.SUCCEEDED)
        self.assertEqual(event.task_type, TaskPricing.TaskType.SUMMARY)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.transcript, self.transcript)
        self.assertEqual(event.summary, summary)
        self.assertEqual(event.model_price, self.model_price)
        self.assertEqual(event.task_pricing, self.task_pricing)
        self.assertEqual(event.provider_request_id, "summary-request-123")
        self.assertEqual(event.input_tokens, 1_500_000)
        self.assertEqual(event.cached_input_tokens, 500_000)
        self.assertEqual(event.output_tokens, 1_000_000)
        self.assertEqual(event.base_cost, Decimal("7.0000000000"))
        self.assertEqual(event.billed_cost, Decimal("10.5000000000"))
        self.assertEqual(event.currency, "USD")
        self.assertEqual(
            event.idempotency_key,
            f"summary:{self.transcript.pk}:general:general:happy-path",
        )

    def test_summarize_pricing_resolution_failure_creates_no_usage_event(self):
        manager = self.manager(model_name="missing-summary-model")

        with self.assertRaises(PricingResolutionError):
            manager.summarize(
                self.transcript.transcript_text,
                self.transcript,
                operation_id="missing-pricing",
            )

        self.assertFalse(UsageEvent.objects.exists())
        self.assertFalse(Summary.objects.exists())
        manager.llm.invoke.assert_not_called()

    def test_summarize_llm_failure_marks_usage_event_failed(self):
        llm = Mock()
        llm.invoke.side_effect = RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            self.manager(llm).summarize(
                self.transcript.transcript_text,
                self.transcript,
                operation_id="invoke-failure",
            )

        self.assertFalse(Summary.objects.exists())
        event = UsageEvent.objects.get()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertIn("provider unavailable", event.calculation_details["lifecycle"]["reason"])

    def test_summarize_response_text_failure_raises_and_requires_reconciliation(self):
        llm = Mock()
        llm.invoke.return_value = self.response()

        with patch(
            "transcription.summary.summary_manager.response_text",
            side_effect=ValueError("invalid response_text"),
        ):
            with self.assertRaisesRegex(ValueError, "invalid response_text"):
                self.manager(llm).summarize(
                    self.transcript.transcript_text,
                    self.transcript,
                    operation_id="response_text-failure",
                )

        self.assertFalse(Summary.objects.exists())
        event = UsageEvent.objects.get()
        self.assertEqual(event.status, UsageEvent.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(event.provider_request_id, "")
        self.assertTrue(
            event.calculation_details["lifecycle"]["provider_response_received"]
        )
        self.assertIn(
            "response_text", event.calculation_details["lifecycle"]["reason"]
        )

    def test_summarize_token_usage_failure_requires_reconciliation(self):
        self._assert_billing_extraction_failure_requires_reconciliation(
            "token_usage"
        )

    def test_summarize_missing_token_usage_keys_requires_reconciliation(self):
        for missing_key in ("input_tokens", "output_tokens"):
            with self.subTest(missing_key=missing_key):
                llm = Mock()
                response = self.response()
                del response.usage_metadata[missing_key]
                llm.invoke.return_value = response

                with patch.dict(os.environ, {"MODEL_ENV": "production"}):
                    self.manager(llm).summarize(
                        self.transcript.transcript_text,
                        self.transcript,
                        operation_id=f"missing-{missing_key}",
                    )

                self.assertTrue(Summary.objects.exists())
                event = UsageEvent.objects.get(
                    idempotency_key=(
                        f"summary:{self.transcript.pk}:general:general:"
                        f"missing-{missing_key}"
                    )
                )
                self.assertEqual(
                    event.status, UsageEvent.Status.RECONCILIATION_REQUIRED
                )
                # Completion did not have enough trustworthy usage data to
                # persist response metadata onto the pending ledger row.
                self.assertEqual(event.provider_request_id, "summary-request-123")
                self.assertIsNone(event.input_tokens)
                self.assertIsNone(event.output_tokens)
                self.assertTrue(
                    event.calculation_details["lifecycle"]
                    ["provider_response_received"]
                )

    def _assert_billing_extraction_failure_requires_reconciliation(
        self, helper_name
    ):
        llm = Mock()
        llm.invoke.return_value = self.response()
        error = ValueError(f"invalid {helper_name}")

        with patch(
            f"transcription.summary.summary_manager.{helper_name}",
            side_effect=error,
        ):
            self.manager(llm).summarize(
                self.transcript.transcript_text,
                self.transcript,
                operation_id=f"{helper_name}-failure",
            )

        self.assertTrue(Summary.objects.exists())
        event = UsageEvent.objects.get()
        self.assertEqual(event.status, UsageEvent.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(event.provider_request_id, "summary-request-123")
        self.assertTrue(
            event.calculation_details["lifecycle"]["provider_response_received"]
        )
        self.assertIn(helper_name, event.calculation_details["lifecycle"]["reason"])

    def test_summarize_completion_failure_requires_reconciliation(self):
        llm = Mock()
        llm.invoke.return_value = self.response()

        with patch(
            "transcription.summary.summary_manager.complete_token_event",
            side_effect=RuntimeError("ledger completion failed"),
        ):
            self.manager(llm).summarize(
                self.transcript.transcript_text,
                self.transcript,
                operation_id="completion-failure",
            )

        # The usable summary remains available when only ledger completion fails.
        self.assertTrue(Summary.objects.exists())
        event = UsageEvent.objects.get()
        self.assertEqual(event.status, UsageEvent.Status.RECONCILIATION_REQUIRED)
        self.assertIsNotNone(event.summary)
        self.assertTrue(
            event.calculation_details["lifecycle"]["provider_response_received"]
        )
        self.assertIn(
            "ledger completion failed",
            event.calculation_details["lifecycle"]["reason"],
        )
