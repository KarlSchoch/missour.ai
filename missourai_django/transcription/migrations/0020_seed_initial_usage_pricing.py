"""Seed the initial, explicitly dated operational pricing configuration.

Rates were verified on 2026-08-09 against the OpenAI model documentation:
https://developers.openai.com/api/docs/models/gpt-transcribe
https://developers.openai.com/api/docs/models/gpt-4.1-mini

These values are starting configuration, not permanently authoritative prices.
Future pricing changes should create new effective-dated records.
"""

from datetime import datetime, timezone
from decimal import Decimal

from django.db import migrations
from django.db.models import Q


EFFECTIVE_FROM = datetime(2026, 8, 9, tzinfo=timezone.utc)


def _effective_record(queryset):
    return queryset.filter(effective_from__lte=EFFECTIVE_FROM).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=EFFECTIVE_FROM)
    )


def seed_initial_pricing(apps, schema_editor):
    ModelPrice = apps.get_model("transcription", "ModelPrice")
    TaskPricing = apps.get_model("transcription", "TaskPricing")

    model_definitions = (
        {
            "provider": "openai",
            "model_name": "gpt-transcribe",
            "billing_unit": "audio_duration",
            "input_rate_per_million": None,
            "cached_input_rate_per_million": None,
            "output_rate_per_million": None,
            "rate_per_minute": Decimal("0.0045"),
            "currency": "USD",
        },
        {
            "provider": "openai",
            "model_name": "gpt-4.1-mini",
            "billing_unit": "text_tokens",
            "input_rate_per_million": Decimal("0.40"),
            "cached_input_rate_per_million": Decimal("0.10"),
            "output_rate_per_million": Decimal("1.60"),
            "rate_per_minute": None,
            "currency": "USD",
        },
    )

    prices = {}
    for definition in model_definitions:
        identity = {
            key: definition[key]
            for key in ("provider", "model_name", "billing_unit", "currency")
        }
        existing = list(_effective_record(ModelPrice.objects.filter(**identity))[:2])
        if len(existing) > 1:
            raise RuntimeError(f"Ambiguous existing pricing for {identity}.")
        if existing:
            model_price = existing[0]
            for field, expected in definition.items():
                if getattr(model_price, field) != expected:
                    raise RuntimeError(
                        f"Existing pricing for {identity} does not match the initial "
                        f"operational configuration ({field})."
                    )
        else:
            model_price = ModelPrice.objects.create(
                **definition,
                effective_from=EFFECTIVE_FROM,
                effective_to=None,
                created_by=None,
            )
        prices[definition["model_name"]] = model_price

    task_definitions = (
        ("transcription", prices["gpt-transcribe"]),
        ("summary", prices["gpt-4.1-mini"]),
        ("tagging", prices["gpt-4.1-mini"]),
    )
    for task_type, model_price in task_definitions:
        existing = list(
            _effective_record(
                TaskPricing.objects.filter(
                    task_type=task_type, model_price=model_price
                )
            )[:2]
        )
        if len(existing) > 1:
            raise RuntimeError(f"Ambiguous existing task pricing for {task_type}.")
        if existing:
            if existing[0].multiplier != Decimal("4"):
                raise RuntimeError(
                    f"Existing task pricing for {task_type} does not use the "
                    "initial 4x multiplier."
                )
        else:
            TaskPricing.objects.create(
                task_type=task_type,
                model_price=model_price,
                multiplier=Decimal("4"),
                effective_from=EFFECTIVE_FROM,
                effective_to=None,
                created_by=None,
            )


class Migration(migrations.Migration):
    dependencies = [("transcription", "0019_alter_usageevent_options")]

    operations = [
        # Pricing may become referenced by immutable usage events, so reversing
        # schema history must not delete operational billing configuration.
        migrations.RunPython(seed_initial_pricing, migrations.RunPython.noop),
    ]
