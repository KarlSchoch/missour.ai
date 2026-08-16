"""Pricing resolution and controlled lifecycle operations for usage events."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from transcription.models import ModelPrice, TaskPricing, UsageEvent

COST_QUANTUM = Decimal("0.0000000001")
TOKEN_RATE_DIVISOR = Decimal("1000000")
SECONDS_PER_MINUTE = Decimal("60")


class PricingResolutionError(Exception):
    """Raised when one unambiguous effective pricing configuration is unavailable."""


class UsageEventLifecycleError(Exception):
    """Raised when a usage event cannot make the requested state transition."""


def _effective_at(queryset, occurred_at):
    return queryset.filter(effective_from__lte=occurred_at).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=occurred_at)
    )


def _get_exactly_one(queryset, description):
    matches = list(queryset[:2])
    if not matches:
        raise PricingResolutionError(f"No effective {description} was found.")
    if len(matches) > 1:
        raise PricingResolutionError(
            f"Multiple effective {description} records were found."
        )
    return matches[0]


def resolve_pricing(task_type, provider, model_name, occurred_at=None):
    occurred_at = occurred_at or timezone.now()
    provider = provider.strip().lower()
    model_name = model_name.strip()
    model_price = _get_exactly_one(
        _effective_at(
            ModelPrice.objects.filter(
                provider=provider, model_name=model_name, currency="USD"
            ),
            occurred_at,
        ).order_by("pk"),
        f"model price for {provider}:{model_name}",
    )
    task_pricing = _get_exactly_one(
        _effective_at(
            TaskPricing.objects.filter(
                task_type=task_type, model_price=model_price
            ),
            occurred_at,
        ).order_by("pk"),
        f"task pricing for {task_type} using {provider}:{model_name}",
    )
    return model_price, task_pricing


def _decimal_string(value):
    return None if value is None else str(value)


def _pricing_snapshot(model_price, task_pricing):
    return {
        "model_price_id": model_price.pk,
        "task_pricing_id": task_pricing.pk,
        "provider": model_price.provider,
        "model_name": model_price.model_name,
        "billing_unit": model_price.billing_unit,
        "currency": model_price.currency,
        "input_rate_per_million": _decimal_string(model_price.input_rate_per_million),
        "cached_input_rate_per_million": _decimal_string(
            model_price.cached_input_rate_per_million
        ),
        "output_rate_per_million": _decimal_string(
            model_price.output_rate_per_million
        ),
        "rate_per_minute": _decimal_string(model_price.rate_per_minute),
        "multiplier": str(task_pricing.multiplier),
    }


def _merge_details(event, additions):
    details = dict(event.calculation_details or {})
    details.update(additions)
    event.calculation_details = details


@transaction.atomic
def create_pending_usage_event(
    *,
    user,
    task_type,
    provider,
    model_name,
    idempotency_key,
    occurred_at=None,
    usage_source=None,
    provider_request_id="",
    transcript=None,
    summary=None,
    tag=None,
    transcription_chunk=None,
    calculation_details=None,
):
    """Resolve pricing before an API call and create its pending ledger row."""
    occurred_at = occurred_at or timezone.now()
    model_price, task_pricing = resolve_pricing(
        task_type, provider, model_name, occurred_at
    )
    if usage_source is None:
        usage_source = (
            UsageEvent.UsageSource.DURATION
            if model_price.billing_unit == ModelPrice.BillingUnit.AUDIO_DURATION
            else UsageEvent.UsageSource.PROVIDER
        )
    details = dict(calculation_details or {})
    details["pricing"] = _pricing_snapshot(model_price, task_pricing)
    return UsageEvent.objects.create(
        user=user,
        task_type=task_type,
        provider=model_price.provider,
        model_name=model_price.model_name,
        occurred_at=occurred_at,
        status=UsageEvent.Status.PENDING,
        billing_unit=model_price.billing_unit,
        usage_source=usage_source,
        model_price=model_price,
        task_pricing=task_pricing,
        multiplier=task_pricing.multiplier,
        currency=model_price.currency,
        calculation_details=details,
        provider_request_id=provider_request_id,
        idempotency_key=idempotency_key,
        transcript=transcript,
        summary=summary,
        tag=tag,
        transcription_chunk=transcription_chunk,
    )


def _as_nonnegative_integer(value, field_name):
    if isinstance(value, bool):
        raise ValidationError({field_name: "Value must be a nonnegative integer."})
    try:
        integer = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(
            {field_name: "Value must be a nonnegative integer."}
        ) from exc
    if integer < 0 or integer != value:
        raise ValidationError({field_name: "Value must be a nonnegative integer."})
    return integer


def _as_nonnegative_decimal(value, field_name):
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(
            {field_name: "Value must be a nonnegative number."}
        ) from exc
    if not decimal_value.is_finite() or decimal_value < 0:
        raise ValidationError({field_name: "Value must be a nonnegative number."})
    return decimal_value


def _quantize_cost(value):
    return value.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)


def _lock_transitionable_event(usage_event):
    event_id = usage_event.pk if isinstance(usage_event, UsageEvent) else usage_event
    if event_id is None:
        raise UsageEventLifecycleError("A saved usage event is required.")
    event = UsageEvent.objects.select_for_update().select_related(
        "model_price", "task_pricing"
    ).get(pk=event_id)
    if event.status not in {
        UsageEvent.Status.PENDING,
        UsageEvent.Status.RECONCILIATION_REQUIRED,
    }:
        raise UsageEventLifecycleError(
            f"Usage event {event.pk} cannot transition from {event.status}."
        )
    return event


@transaction.atomic
def complete_token_event(
    usage_event,
    *,
    input_tokens,
    output_tokens,
    cached_input_tokens=0,
    provider_request_id="",
    calculation_details=None,
):
    """Complete text usage; input_tokens is the provider's total input count."""
    event = _lock_transitionable_event(usage_event)
    if event.billing_unit != ModelPrice.BillingUnit.TEXT_TOKENS:
        raise UsageEventLifecycleError("The usage event is not billed by text tokens.")

    total_input = _as_nonnegative_integer(input_tokens, "input_tokens")
    cached_input = _as_nonnegative_integer(
        cached_input_tokens, "cached_input_tokens"
    )
    output = _as_nonnegative_integer(output_tokens, "output_tokens")
    if cached_input > total_input:
        raise ValidationError(
            {"cached_input_tokens": "Cached input cannot exceed total input."}
        )
    uncached_input = total_input - cached_input
    price = event.model_price
    cached_rate = price.cached_input_rate_per_million
    if cached_input and cached_rate is None:
        raise UsageEventLifecycleError(
            "Cached input was reported but the model price has no cached-input rate."
        )

    with localcontext() as context:
        context.prec = 50
        input_cost = (
            Decimal(uncached_input)
            * price.input_rate_per_million
            / TOKEN_RATE_DIVISOR
        )
        cached_cost = (
            Decimal(cached_input)
            * (cached_rate or Decimal("0"))
            / TOKEN_RATE_DIVISOR
        )
        output_cost = (
            Decimal(output)
            * price.output_rate_per_million
            / TOKEN_RATE_DIVISOR
        )
        base_cost = _quantize_cost(input_cost + cached_cost + output_cost)
        billed_cost = _quantize_cost(base_cost * event.multiplier)

    event.input_tokens = uncached_input
    event.cached_input_tokens = cached_input
    event.output_tokens = output
    event.base_cost = base_cost
    event.billed_cost = billed_cost
    event.status = UsageEvent.Status.SUCCEEDED
    if provider_request_id:
        event.provider_request_id = provider_request_id
    _merge_details(
        event,
        {
            "calculation": {
                "provider_total_input_tokens": total_input,
                "uncached_input_tokens": uncached_input,
                "cached_input_tokens": cached_input,
                "output_tokens": output,
                "input_rate_per_million": str(price.input_rate_per_million),
                "cached_input_rate_per_million": _decimal_string(cached_rate),
                "output_rate_per_million": str(price.output_rate_per_million),
                "token_rate_divisor": str(TOKEN_RATE_DIVISOR),
                "base_cost": str(base_cost),
                "multiplier": str(event.multiplier),
                "billed_cost": str(billed_cost),
                "rounding": "ROUND_HALF_UP",
                **dict(calculation_details or {}),
            }
        },
    )
    event.save()
    return event


@transaction.atomic
def complete_duration_event(
    usage_event,
    *,
    audio_duration_seconds,
    provider_request_id="",
    calculation_details=None,
):
    """Complete an audio-duration usage event and calculate its cost."""
    event = _lock_transitionable_event(usage_event)
    if event.billing_unit != ModelPrice.BillingUnit.AUDIO_DURATION:
        raise UsageEventLifecycleError("The usage event is not billed by duration.")

    duration = _as_nonnegative_decimal(
        audio_duration_seconds, "audio_duration_seconds"
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    price = event.model_price
    with localcontext() as context:
        context.prec = 50
        base_cost = _quantize_cost(
            duration / SECONDS_PER_MINUTE * price.rate_per_minute
        )
        billed_cost = _quantize_cost(base_cost * event.multiplier)

    event.audio_duration_seconds = duration
    event.base_cost = base_cost
    event.billed_cost = billed_cost
    event.status = UsageEvent.Status.SUCCEEDED
    if provider_request_id:
        event.provider_request_id = provider_request_id
    _merge_details(
        event,
        {
            "calculation": {
                "audio_duration_seconds": str(duration),
                "seconds_per_minute": str(SECONDS_PER_MINUTE),
                "rate_per_minute": str(price.rate_per_minute),
                "base_cost": str(base_cost),
                "multiplier": str(event.multiplier),
                "billed_cost": str(billed_cost),
                "rounding": "ROUND_HALF_UP",
                **dict(calculation_details or {}),
            }
        },
    )
    event.save()
    return event


def _transition_without_cost(usage_event, status, reason, calculation_details):
    event = _lock_transitionable_event(usage_event)
    event.status = status
    _merge_details(
        event,
        {
            "lifecycle": {
                "reason": str(reason),
                **dict(calculation_details or {}),
            }
        },
    )
    event.save()
    return event


@transaction.atomic
def mark_failed(usage_event, *, reason, calculation_details=None):
    """Close a pending event as a non-billable failure."""
    return _transition_without_cost(
        usage_event, UsageEvent.Status.FAILED, reason, calculation_details
    )


@transaction.atomic
def mark_reconciliation_required(
    usage_event, *, reason, calculation_details=None
):
    """Flag an event whose final usage or cost could not be determined safely."""
    return _transition_without_cost(
        usage_event,
        UsageEvent.Status.RECONCILIATION_REQUIRED,
        reason,
        calculation_details,
    )
