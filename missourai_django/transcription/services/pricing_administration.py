"""Confirmed, transactional pricing administration and deployment readiness."""
import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from transcription.models import ModelPrice, TaskPricing, PricingWriteLock
from .pricing import resolve_pricing, PricingResolutionError


class PricingSelectionRequired(Exception):
    """More than one record could be the intended supersession target."""

    def __init__(self, candidates, *, conflict=False):
        self.candidates = candidates
        self.conflict = conflict
        super().__init__("Multiple possible pricing records were found.")


def _customer_pricing(price, multiplier):
    """Return display-safe customer rates calculated with Decimal arithmetic."""
    fields = (
        "input_rate_per_million",
        "cached_input_rate_per_million",
        "output_rate_per_million",
        "rate_per_minute",
    )
    return {
        "billing_unit": price.billing_unit,
        "currency": price.currency,
        **{
            field: str(getattr(price, field) * multiplier)
            if getattr(price, field) is not None else None
            for field in fields
        },
    }


def _task_pricing_impact(task_type, model_name, current_price, current_multiplier,
                         proposed_price, proposed_multiplier):
    return {
        "task_type": task_type,
        "model_name": model_name,
        "multiplier": str(proposed_multiplier),
        "current_customer_pricing": (
            _customer_pricing(current_price, current_multiplier)
            if current_price is not None and current_multiplier is not None else None
        ),
        "proposed_customer_pricing": _customer_pricing(
            proposed_price, proposed_multiplier,
        ),
        "ready": True,
    }


def configured_models():
    return {
        "transcription": settings.TRANSCRIPTION_MODEL,
        "summary": settings.SUMMARY_MODEL,
        "tagging": settings.TAGGING_MODEL,
    }


def readiness(at=None):
    at = at or timezone.now()
    rows = []
    for task, model in configured_models().items():
        row = {"task_type": task, "model_name": model, "ready": False}
        try:
            price, pricing = resolve_pricing(task, "openai", model, at)
            price.full_clean()
            pricing.full_clean()
            expected = "audio_duration" if task == "transcription" else "text_tokens"
            if price.billing_unit != expected:
                raise ValidationError(f"{task} requires {expected} pricing.")
            row.update(
                ready=True,
                model_price_id=price.pk,
                task_pricing_id=pricing.pk,
                currency=price.currency,
                billing_unit=price.billing_unit,
                input_rate_per_million=price.input_rate_per_million,
                cached_input_rate_per_million=price.cached_input_rate_per_million,
                output_rate_per_million=price.output_rate_per_million,
                rate_per_minute=price.rate_per_minute,
                multiplier=pricing.multiplier,
            )
        except (PricingResolutionError, ValidationError) as exc:
            row["error"] = str(exc)
        rows.append(row)
    return rows


def validate_configuration(at=None):
    errors = []
    for model in (ModelPrice, TaskPricing):
        for record in model.objects.all():
            try:
                record.full_clean()
                if isinstance(record, ModelPrice) and record.currency != "USD":
                    raise ValidationError("Only USD is supported.")
            except ValidationError as exc:
                errors.append(f"{model.__name__} #{record.pk}: {exc}")
    # The runtime resolver does not disambiguate by billing unit.
    prices = list(ModelPrice.objects.order_by("provider", "model_name", "currency", "effective_from"))
    for index, price in enumerate(prices):
        for other in prices[index + 1:]:
            if (price.provider, price.model_name, price.currency) != (other.provider, other.model_name, other.currency):
                continue
            if price.effective_to is None or other.effective_from < price.effective_to:
                errors.append(f"Ambiguous model-price periods: #{price.pk} and #{other.pk}.")
    states = readiness(at)
    errors.extend(f"{row['task_type']}: {row['error']}" for row in states if not row["ready"])
    return states, errors


def fingerprint():
    payload = {
        "models": list(ModelPrice.objects.order_by("pk").values()),
        "tasks": list(TaskPricing.objects.order_by("pk").values()),
        "configuration": configured_models(),
    }
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


@transaction.atomic
def change_pricing(kind, data, user, *, preview=False, expected_fingerprint=None):
    # SQLite IMMEDIATE serializes writers; on PostgreSQL this row also protects
    # empty scopes where locking existing price rows alone would be insufficient.
    PricingWriteLock.objects.select_for_update().get(pk=1)
    before = fingerprint()
    if expected_fingerprint is not None and before != expected_fingerprint:
        raise ValidationError("Pricing or active models changed. Preview again before confirming.")
    data = dict(data)
    selected_supersedes = data.pop("selected_supersedes", None)
    immediate = data.pop("activate_now", False)
    start = data["effective_from"]
    if not immediate and start < timezone.now():
        raise ValidationError("Schedule future pricing or select immediate activation; backdating is not allowed.")
    model = ModelPrice if kind == "model" else TaskPricing
    candidate = model(**data, created_by=user)
    if kind == "model":
        candidate.model_name = candidate.model_name.strip()
        if candidate.currency != "USD":
            raise ValidationError("Only USD is supported.")
        if immediate and candidate.model_name not in configured_models().values():
            raise ValidationError("Immediate activation requires a configured model.")
        for task, name in configured_models().items():
            expected = "audio_duration" if task == "transcription" else "text_tokens"
            if immediate and name == candidate.model_name and candidate.billing_unit != expected:
                raise ValidationError(f"{task} requires {expected} pricing.")
        identity = ("provider", "model_name", "currency")
    else:
        identity = ("task_type", "model_price_id")
        price = candidate.model_price
        if price.currency != "USD":
            raise ValidationError("Only USD is supported.")
        if immediate and configured_models()[candidate.task_type] != price.model_name:
            raise ValidationError("Immediate activation requires the configured task model.")
        expected = "audio_duration" if candidate.task_type == "transcription" else "text_tokens"
        if price.billing_unit != expected:
            raise ValidationError(f"This task requires {expected} pricing.")
    scope = model.objects.select_for_update().filter(**{
        key: getattr(candidate, key) for key in identity
    })
    applicable = scope.filter(effective_from__lte=start).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=start)
    )
    applicable = list(applicable.order_by("effective_from", "pk"))
    if selected_supersedes is not None:
        old = next((record for record in applicable if record.pk == selected_supersedes), None)
        if old is None:
            raise ValidationError("The selected pricing record is no longer applicable. Preview again.")
    elif len(applicable) == 1:
        old = applicable[0]
    elif len(applicable) > 1:
        raise PricingSelectionRequired(applicable, conflict=True)
    else:
        old = None
    closed = []
    carried_task_prices = []
    impacts = []
    if old:
        if any(getattr(old, key) != getattr(candidate, key) for key in identity):
            raise ValidationError("Supersession must keep the same pricing scope.")
        if start <= old.effective_from:
            raise ValidationError("A replacement must start after the selected record begins.")
        previous_end = old.effective_to
        if candidate.effective_to is None and previous_end is not None:
            candidate.effective_to = previous_end
        if kind == "model":
            for task_price in old.task_pricings.select_for_update().order_by("pk"):
                if task_price.effective_from >= start:
                    raise ValidationError("Existing future task pricing conflicts with this boundary.")
                if task_price.effective_to is None or task_price.effective_to > start:
                    expected_unit = "audio_duration" if task_price.task_type == "transcription" else "text_tokens"
                    if candidate.billing_unit != expected_unit:
                        raise ValidationError(
                            f"{task_price.task_type} requires {expected_unit} pricing; "
                            "its multiplier cannot be carried forward."
                        )
                    carried_task_prices.append(TaskPricing(
                        task_type=task_price.task_type,
                        model_price=candidate,
                        multiplier=task_price.multiplier,
                        effective_from=start,
                        effective_to=task_price.effective_to,
                        created_by=user,
                    ))
                    impacts.append(_task_pricing_impact(
                        task_price.task_type,
                        candidate.model_name,
                        old,
                        task_price.multiplier,
                        candidate,
                        task_price.multiplier,
                    ))
                    task_price.effective_to = start
                    task_price.save()
                    closed.append({"kind": "task", "id": task_price.pk, "effective_to": start})
        old.effective_to = start
        old.save()
        closed.append({"kind": kind, "id": old.pk, "effective_to": start})
    candidate.full_clean()
    if kind == "task":
        impacts.append(_task_pricing_impact(
            candidate.task_type,
            candidate.model_price.model_name,
            candidate.model_price if old else None,
            old.multiplier if old else None,
            candidate.model_price,
            candidate.multiplier,
        ))
    if kind == "model":
        overlaps = ModelPrice.objects.filter(provider=candidate.provider, model_name=candidate.model_name, currency=candidate.currency)
        if candidate.effective_to:
            overlaps = overlaps.filter(effective_from__lt=candidate.effective_to)
        if overlaps.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=start)).exists():
            raise ValidationError("Model-price periods cannot overlap, including across billing units.")
    created = []
    if not preview:
        candidate.save()
        if kind == "model" and old:
            for task_price in carried_task_prices:
                task_price.model_price = candidate
                task_price.save()
                created.append(task_price)
    else:
        # Exercise the same closures/validation, then roll back all writes.
        # No candidate row or historical change is persisted by a preview.
        transaction.set_rollback(True)
    if preview and kind == "model" and old:
        created.extend(carried_task_prices)
    return candidate, closed, created, impacts, before
