"""Confirmed, transactional pricing administration and deployment readiness."""
import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from transcription.models import ModelPrice, TaskPricing, PricingWriteLock
from .pricing import resolve_pricing, PricingResolutionError


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
            row.update(ready=True, model_price_id=price.pk, task_pricing_id=pricing.pk)
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
    supersedes = data.pop("supersedes", None)
    immediate = data.pop("activate_now", False)
    start = data["effective_from"]
    if not immediate and start < timezone.now():
        raise ValidationError("Schedule future pricing or select immediate activation; backdating is not allowed.")
    model = ModelPrice if kind == "model" else TaskPricing
    old = model.objects.select_for_update().filter(pk=supersedes).first() if supersedes else None
    if supersedes and old is None:
        raise ValidationError("The record to supersede no longer exists.")
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
    closed = []
    if old:
        if any(getattr(old, key) != getattr(candidate, key) for key in identity):
            raise ValidationError("Supersession must keep the same pricing scope.")
        if old.effective_to is not None or start <= old.effective_from:
            raise ValidationError("Supersede an open-ended record with a later effective start.")
        if kind == "model":
            for task_price in old.task_pricings.select_for_update().order_by("pk"):
                if task_price.effective_from >= start:
                    raise ValidationError("Existing future task pricing conflicts with this boundary.")
                if task_price.effective_to is None or task_price.effective_to > start:
                    task_price.effective_to = start
                    task_price.save()
                    closed.append({"kind": "task", "id": task_price.pk, "effective_to": start})
        old.effective_to = start
        old.save()
        closed.append({"kind": kind, "id": old.pk, "effective_to": start})
    candidate.full_clean()
    if kind == "model":
        overlaps = ModelPrice.objects.filter(provider=candidate.provider, model_name=candidate.model_name, currency=candidate.currency)
        if candidate.effective_to:
            overlaps = overlaps.filter(effective_from__lt=candidate.effective_to)
        from django.db.models import Q
        if overlaps.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=start)).exists():
            raise ValidationError("Model-price periods cannot overlap, including across billing units.")
    if not preview:
        candidate.save()
    else:
        # Exercise the same closures/validation, then roll back all writes.
        # No candidate row or historical change is persisted by a preview.
        transaction.set_rollback(True)
    return candidate, closed, before
