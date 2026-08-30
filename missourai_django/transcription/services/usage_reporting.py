"""Read-only reporting queries over the immutable usage ledger."""

from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from transcription.models import UsageEvent


DEFAULT_CURRENCY = "USD"


class UsageReportFilterError(ValueError):
    """Raised when a usage-report filter cannot be interpreted safely."""


def get_month_bounds(month=None, report_timezone=None):
    """Return a UTC half-open range for a YYYY-MM calendar month."""
    report_timezone = report_timezone or datetime_timezone.utc
    if month is None:
        current = timezone.now().astimezone(report_timezone)
        year, month_number = current.year, current.month
    else:
        try:
            parsed = datetime.strptime(month, "%Y-%m")
        except (TypeError, ValueError) as exc:
            raise UsageReportFilterError("month must use YYYY-MM format.") from exc
        year, month_number = parsed.year, parsed.month

    start = datetime(year, month_number, 1, tzinfo=report_timezone)
    if month_number == 12:
        end = datetime(year + 1, 1, 1, tzinfo=report_timezone)
    else:
        end = datetime(year, month_number + 1, 1, tzinfo=report_timezone)

    now = timezone.now()
    effective_end = min(end, now) if start <= now < end else end
    return start, effective_end


def get_usage_queryset(*, start, end, user=None):
    queryset = UsageEvent.objects.filter(
        occurred_at__gte=start,
        occurred_at__lt=end,
    ).select_related(
        "user",
        "model_price",
        "task_pricing",
        "transcript",
        "summary",
        "tag",
        "transcription_chunk",
    )
    if user is not None:
        queryset = queryset.filter(user=user)
    return queryset


def apply_event_filters(
    queryset,
    *,
    task_type=None,
    model_name=None,
    status=None,
):
    if task_type:
        queryset = queryset.filter(task_type=task_type)
    if model_name:
        queryset = queryset.filter(model_name=model_name)
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def _cost_totals(queryset):
    totals = queryset.aggregate(
        event_count=Count("id"),
        base_cost=Sum("base_cost"),
        billed_cost=Sum("billed_cost"),
    )
    return {
        "event_count": totals["event_count"],
        "base_cost": totals["base_cost"] or Decimal("0"),
        "billed_cost": totals["billed_cost"] or Decimal("0"),
    }


def get_user_summary(queryset):
    return _cost_totals(queryset.filter(status=UsageEvent.Status.SUCCEEDED))


def get_organization_summary(queryset):
    return get_user_summary(queryset)


def get_task_breakdown(queryset):
    rows = (
        queryset.filter(status=UsageEvent.Status.SUCCEEDED)
        .values("task_type")
        .annotate(
            event_count=Count("id"),
            base_cost=Sum("base_cost"),
            billed_cost=Sum("billed_cost"),
        )
        .order_by("task_type")
    )
    return list(rows)


def get_user_totals(queryset):
    rows = (
        queryset.filter(status=UsageEvent.Status.SUCCEEDED)
        .values("user_id", "user__username")
        .annotate(
            event_count=Count("id"),
            base_cost=Sum("base_cost"),
            billed_cost=Sum("billed_cost"),
        )
        .order_by("user__username", "user_id")
    )
    return list(rows)


def get_status_counts(queryset):
    return list(
        queryset.values("status")
        .annotate(event_count=Count("id"))
        .order_by("status")
    )


def get_event_details(queryset):
    return queryset.order_by("-occurred_at", "-id")


def get_applied_pricing_periods(queryset):
    """Describe pricing snapshots contributing to succeeded-event totals."""
    rows = (
        queryset.filter(status=UsageEvent.Status.SUCCEEDED)
        .values(
            "task_type",
            "provider",
            "model_name",
            "billing_unit",
            "currency",
            "model_price_id",
            "model_price__effective_from",
            "model_price__effective_to",
            "model_price__input_rate_per_million",
            "model_price__cached_input_rate_per_million",
            "model_price__output_rate_per_million",
            "model_price__rate_per_minute",
            "task_pricing_id",
            "task_pricing__effective_from",
            "task_pricing__effective_to",
            "multiplier",
        )
        .annotate(
            event_count=Count("id"),
            base_cost=Sum("base_cost"),
            billed_cost=Sum("billed_cost"),
        )
        .order_by(
            "task_type",
            "model_name",
            "model_price__effective_from",
            "task_pricing__effective_from",
        )
    )
    return list(rows)


def get_report_month_label(start):
    return start.strftime("%Y-%m")
