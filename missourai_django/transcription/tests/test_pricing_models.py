from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from transcription.models import ModelPrice, TaskPricing


class PricingEffectivePeriodTests(TestCase):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def create_model_price(self, **overrides):
        values = {
            "provider": ModelPrice.Provider.OPENAI,
            "model_name": "gpt-test",
            "billing_unit": ModelPrice.BillingUnit.TEXT_TOKENS,
            "input_rate_per_million": Decimal("1.00"),
            "output_rate_per_million": Decimal("2.00"),
            "currency": "USD",
            "effective_from": self.start,
            "effective_to": None,
        }
        values.update(overrides)
        return ModelPrice.objects.create(**values)

    def create_task_pricing(self, model_price, **overrides):
        values = {
            "task_type": TaskPricing.TaskType.SUMMARY,
            "model_price": model_price,
            "multiplier": Decimal("1.25"),
            "effective_from": self.start,
            "effective_to": None,
        }
        values.update(overrides)
        return TaskPricing.objects.create(**values)

    def test_second_open_ended_model_price_is_rejected(self):
        self.create_model_price()

        with self.assertRaisesMessage(
            ValidationError,
            "Effective periods cannot overlap for the same provider, model, "
            "billing unit, and currency.",
        ):
            self.create_model_price(effective_from=self.start + timedelta(days=30))

    def test_second_open_ended_task_pricing_is_rejected(self):
        model_price = self.create_model_price()
        self.create_task_pricing(model_price)

        with self.assertRaisesMessage(
            ValidationError,
            "Effective periods cannot overlap for the same task and model price.",
        ):
            self.create_task_pricing(
                model_price,
                effective_from=self.start + timedelta(days=30),
            )

    def test_overlapping_model_price_periods_are_rejected(self):
        self.create_model_price(effective_to=self.start + timedelta(days=60))

        with self.assertRaisesMessage(
            ValidationError,
            "Effective periods cannot overlap for the same provider, model, "
            "billing unit, and currency.",
        ):
            self.create_model_price(
                effective_from=self.start + timedelta(days=30),
                effective_to=self.start + timedelta(days=90),
            )

    def test_overlapping_task_pricing_periods_are_rejected(self):
        model_price = self.create_model_price(
            effective_to=self.start + timedelta(days=120)
        )
        self.create_task_pricing(
            model_price,
            effective_to=self.start + timedelta(days=60),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Effective periods cannot overlap for the same task and model price.",
        ):
            self.create_task_pricing(
                model_price,
                effective_from=self.start + timedelta(days=30),
                effective_to=self.start + timedelta(days=90),
            )
