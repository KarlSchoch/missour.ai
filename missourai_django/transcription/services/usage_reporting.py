"""Reporting over stored ledger amounts; never reprice historical usage."""
import re
from datetime import datetime, timezone as dt_timezone

from django.db.models import Count, Sum
from django.utils import timezone

from transcription.models import UsageEvent


def get_month_bounds(month=None):
    """UTC calendar bounds, clipped to now for the current month, [start, end)."""
    now = timezone.now()
    month = month if month is not None else now.astimezone(dt_timezone.utc).strftime('%Y-%m')
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}', month):
        raise ValueError('month must use YYYY-MM format.')
    try:
        year, number = map(int, month.split('-'))
        start = datetime(year, number, 1, tzinfo=dt_timezone.utc)
        end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=dt_timezone.utc)
    except ValueError as exc:
        raise ValueError('month must identify a valid calendar month before 9999-12.') from exc
    return start, now if start <= now < end else end


def get_event_details(*, start, end, user_id=None, **filters):
    events = UsageEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    if user_id is not None:
        events = events.filter(user_id=user_id)
    for key in ('task_type', 'model_name', 'status'):
        if filters.get(key):
            events = events.filter(**{key: filters[key]})
    return events.select_related('user').order_by('-occurred_at', '-id')


def _totals(events, *fields):
    return events.filter(status=UsageEvent.Status.SUCCEEDED).order_by().values(
        *fields, 'currency'
    ).annotate(event_count=Count('id'), base_cost=Sum('base_cost'), billed_cost=Sum('billed_cost')).order_by(*fields, 'currency')


def get_user_summary(events):
    return _totals(events)


def get_organization_summary(events):
    return _totals(events)


def get_user_totals(events):
    return _totals(events, 'user_id')


def get_task_breakdown(events):
    return _totals(events, 'task_type')


def get_status_counts(events):
    return events.order_by().values('status').annotate(event_count=Count('id')).order_by('status')


def get_applied_pricing_periods(events):
    return _totals(
        events, 'task_type', 'provider', 'model_name', 'billing_unit',
        'model_price_id', 'task_pricing_id', 'multiplier',
        'model_price__effective_from', 'model_price__effective_to',
        'task_pricing__effective_from', 'task_pricing__effective_to',
        'model_price__input_rate_per_million',
        'model_price__cached_input_rate_per_million',
        'model_price__output_rate_per_million', 'model_price__rate_per_minute',
    )
