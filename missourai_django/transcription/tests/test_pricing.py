from datetime import datetime, timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from transcription.models import ModelPrice, TaskPricing, UsageEvent
from transcription.services.pricing import (
    PricingResolutionError,
    UsageEventLifecycleError,
    complete_duration_event,
    complete_token_event,
    create_pending_usage_event,
    mark_failed,
    resolve_pricing,
)


class ResolvePricingTests(TestCase):
    occurred_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def model_price(self, **overrides):
        values = {
            "provider": ModelPrice.Provider.OPENAI,
            "model_name": "gpt-resolve-pricing-test",
            "billing_unit": ModelPrice.BillingUnit.TEXT_TOKENS,
            "input_rate_per_million": Decimal("1.25"),
            "output_rate_per_million": Decimal("5.00"),
            "currency": "USD",
            "effective_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "effective_to": None,
        }
        values.update(overrides)
        return ModelPrice(**values)

    def test_raises_when_no_model_price_matches(self):
        self.model_price(model_name="another-model").save()

        with self.assertRaises(PricingResolutionError):
            resolve_pricing(
                TaskPricing.TaskType.SUMMARY,
                ModelPrice.Provider.OPENAI,
                "gpt-resolve-pricing-test",
                self.occurred_at,
            )

    def test_raises_when_multiple_model_prices_match(self):
        ModelPrice.objects.bulk_create(
            [
                self.model_price(),
                self.model_price(
                    effective_from=datetime(2026, 2, 1, tzinfo=timezone.utc)
                ),
            ]
        )

        with self.assertRaises(PricingResolutionError):
            resolve_pricing(
                TaskPricing.TaskType.SUMMARY,
                ModelPrice.Provider.OPENAI,
                "gpt-resolve-pricing-test",
                self.occurred_at,
            )

    def test_returns_effective_model_price_and_task_pricing(self):
        model_price = self.model_price()
        model_price.save()
        task_pricing = TaskPricing.objects.create(
            task_type=TaskPricing.TaskType.SUMMARY,
            model_price=model_price,
            multiplier=Decimal("1.75"),
            effective_from=datetime(2026, 3, 1, tzinfo=timezone.utc),
            effective_to=None,
        )

        resolved_model_price, resolved_task_pricing = resolve_pricing(
            TaskPricing.TaskType.SUMMARY,
            ModelPrice.Provider.OPENAI,
            "gpt-resolve-pricing-test",
            self.occurred_at,
        )

        self.assertEqual(resolved_model_price, model_price)
        self.assertEqual(resolved_task_pricing, task_pricing)
        self.assertEqual(resolved_model_price.input_rate_per_million, Decimal("1.25"))
        self.assertEqual(resolved_model_price.output_rate_per_million, Decimal("5.00"))
        self.assertEqual(resolved_task_pricing.multiplier, Decimal("1.75"))


class UsageEventServiceTests(TestCase):
    occurred_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="pricing-service-user"
        )

    def create_pricing(self, *, billing_unit, model_name, multiplier=Decimal("1.5")):
        model_price_values = {
            "provider": ModelPrice.Provider.OPENAI,
            "model_name": model_name,
            "billing_unit": billing_unit,
            "currency": "USD",
            "effective_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "effective_to": None,
        }
        if billing_unit == ModelPrice.BillingUnit.TEXT_TOKENS:
            model_price_values.update(
                input_rate_per_million=Decimal("1.25"),
                cached_input_rate_per_million=Decimal("0.25"),
                output_rate_per_million=Decimal("5.00"),
            )
        else:
            model_price_values["rate_per_minute"] = Decimal("0.60")

        model_price = ModelPrice.objects.create(**model_price_values)
        TaskPricing.objects.create(
            task_type=TaskPricing.TaskType.SUMMARY,
            model_price=model_price,
            multiplier=multiplier,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            effective_to=None,
        )
        return model_price

    def create_pending_event(self, *, billing_unit, model_name, idempotency_key):
        self.create_pricing(billing_unit=billing_unit, model_name=model_name)
        return create_pending_usage_event(
            user=self.user,
            task_type=TaskPricing.TaskType.SUMMARY,
            provider=ModelPrice.Provider.OPENAI,
            model_name=model_name,
            idempotency_key=idempotency_key,
            occurred_at=self.occurred_at,
        )

    def test_create_pending_event_does_not_create_record_when_pricing_fails(self):
        """
        Validates that create_pending_usage_event raises an error when a matching
        db entry does not exist
        """
        with self.assertRaises(PricingResolutionError):
            create_pending_usage_event(
                user=self.user,
                task_type=TaskPricing.TaskType.SUMMARY,
                provider=ModelPrice.Provider.OPENAI,
                model_name="missing-model",
                idempotency_key="missing-pricing",
                occurred_at=self.occurred_at,
            )

        self.assertFalse(UsageEvent.objects.exists())

    def test_create_pending_event_creates_incomplete_pending_record(self):
        
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            model_name="pending-text-model",
            idempotency_key="pending-text",
        )
        event.refresh_from_db()

        self.assertEqual(event.status, UsageEvent.Status.PENDING)
        for field_name in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "audio_duration_seconds",
            "base_cost",
            "billed_cost",
        ):
            self.assertIsNone(getattr(event, field_name))

    def test_complete_token_event_rejects_terminal_status(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            model_name="terminal-text-model",
            idempotency_key="terminal-text",
        )
        mark_failed(event, reason="test terminal state")

        with self.assertRaises(UsageEventLifecycleError):
            complete_token_event(event.pk, input_tokens=1, output_tokens=1)

        event.refresh_from_db()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)

    def test_complete_token_event_rejects_non_token_billing(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.AUDIO_DURATION,
            model_name="wrong-unit-duration-model",
            idempotency_key="wrong-unit-duration",
        )

        with self.assertRaises(UsageEventLifecycleError):
            complete_token_event(event, input_tokens=1, output_tokens=1)

        event.refresh_from_db()
        self.assertEqual(event.status, UsageEvent.Status.PENDING)

    def test_complete_token_event_records_usage_costs_and_succeeds(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            model_name="completed-text-model",
            idempotency_key="completed-text",
        )

        complete_token_event(
            event,
            input_tokens=2_000_000,
            cached_input_tokens=500_000,
            output_tokens=1_000_000,
        )
        event.refresh_from_db()

        self.assertEqual(event.status, UsageEvent.Status.SUCCEEDED)
        self.assertEqual(event.input_tokens, 1_500_000)
        self.assertEqual(event.cached_input_tokens, 500_000)
        self.assertEqual(event.output_tokens, 1_000_000)
        self.assertEqual(event.base_cost, Decimal("7.0000000000"))
        self.assertEqual(event.billed_cost, Decimal("10.5000000000"))

    def test_complete_duration_event_rejects_terminal_status(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.AUDIO_DURATION,
            model_name="terminal-duration-model",
            idempotency_key="terminal-duration",
        )
        mark_failed(event, reason="test terminal state")

        with self.assertRaises(UsageEventLifecycleError):
            complete_duration_event(event.pk, audio_duration_seconds=60)

        event.refresh_from_db()
        self.assertEqual(event.status, UsageEvent.Status.FAILED)

    def test_complete_duration_event_rejects_non_duration_billing(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            model_name="wrong-unit-text-model",
            idempotency_key="wrong-unit-text",
        )

        with self.assertRaises(UsageEventLifecycleError):
            complete_duration_event(event, audio_duration_seconds=60)

        event.refresh_from_db()
        self.assertEqual(event.status, UsageEvent.Status.PENDING)

    def test_complete_duration_event_records_usage_costs_and_succeeds(self):
        event = self.create_pending_event(
            billing_unit=ModelPrice.BillingUnit.AUDIO_DURATION,
            model_name="completed-duration-model",
            idempotency_key="completed-duration",
        )

        complete_duration_event(event, audio_duration_seconds=90)
        event.refresh_from_db()

        self.assertEqual(event.status, UsageEvent.Status.SUCCEEDED)
        self.assertEqual(event.audio_duration_seconds, Decimal("90.000000"))
        self.assertEqual(event.base_cost, Decimal("0.9000000000"))
        self.assertEqual(event.billed_cost, Decimal("1.3500000000"))
