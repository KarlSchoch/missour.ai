from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from transcription.models import ModelPrice, TaskPricing, UsageEvent


class UsageTestCase(TestCase):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="usage-owner")
        cls.other = get_user_model().objects.create_user(username="usage-other")
        cls.viewer = get_user_model().objects.create_user(username="usage-viewer")
        cls.viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label="transcription", codename="view_all_usage",
        ))
        cls.price = ModelPrice.objects.create(
            provider=ModelPrice.Provider.OPENAI,
            model_name="usage-test-model",
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            input_rate_per_million=Decimal("1"),
            output_rate_per_million=Decimal("2"),
            effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        cls.pricing = {}
        for task in (TaskPricing.TaskType.SUMMARY, TaskPricing.TaskType.TAGGING):
            cls.pricing[task] = TaskPricing.objects.create(
                task_type=task, model_price=cls.price,
                multiplier=Decimal("2"), effective_from=cls.price.effective_from,
            )

    def event(self, **overrides):
        values = dict(
            user=self.user, task_type=TaskPricing.TaskType.SUMMARY,
            model_price=self.price, provider=self.price.provider,
            model_name=self.price.model_name, billing_unit=self.price.billing_unit,
            usage_source=UsageEvent.UsageSource.PROVIDER,
            occurred_at=self.start, status=UsageEvent.Status.SUCCEEDED,
            input_tokens=100, output_tokens=50,
            base_cost=Decimal("1.25"), billed_cost=Decimal("2.50"),
            multiplier=Decimal("2"), currency="USD", idempotency_key=str(uuid4()),
        )
        values.update(overrides)
        values.setdefault("task_pricing", self.pricing[values["task_type"]])
        return UsageEvent.objects.create(**values)
