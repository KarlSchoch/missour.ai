"""Authenticated, read-only usage reporting endpoints."""
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ModelPrice, TaskPricing
from .services import usage_reporting as reporting
from . import usage_serializers as serializers


class UsagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class UsageAPIView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'head', 'options']

    def can_view_all(self):
        return self.request.user.has_perm('transcription.view_all_usage')

    def report_context(self):
        filters = serializers.UsageFiltersSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        data = dict(filters.validated_data)
        try:
            start, end = reporting.get_month_bounds(data.pop('month', None))
        except ValueError as exc:
            raise ValidationError({'month': str(exc)}) from exc
        user_id = data.pop('user_id', None)
        if not self.can_view_all():
            if user_id is not None and user_id != self.request.user.pk:
                raise PermissionDenied('You cannot view another user\'s usage.')
            user_id = self.request.user.pk
        if user_id is not None and not get_user_model().objects.filter(pk=user_id).exists():
            raise NotFound('User not found.')
        events = reporting.get_event_details(start=start, end=end, user_id=user_id, **data)
        return start, end, user_id, events

    def serialize(self, serializer, rows):
        return serializer(rows, many=True, context={'can_view_all_usage': self.can_view_all()}).data


class UsageSummaryAPIView(UsageAPIView):
    def get(self, request):
        start, end, user_id, events = self.report_context()
        totals = reporting.get_user_summary(events) if user_id else reporting.get_organization_summary(events)
        payload = {
            'period': {'month': start.strftime('%Y-%m'), 'start': start, 'end': end, 'timezone': 'UTC'},
            'scope': {'kind': 'user' if user_id else 'organization', 'user_id': user_id},
            'totals': self.serialize(serializers.OverallMonthlyTotalSerializer, totals),
            'tasks': self.serialize(serializers.MonthlyTaskTotalSerializer, reporting.get_task_breakdown(events)),
            'status_counts': list(reporting.get_status_counts(events)),
        }
        if self.can_view_all():
            payload['pricing_periods'] = self.serialize(serializers.AppliedPricingPeriodSerializer, reporting.get_applied_pricing_periods(events))
            if user_id is None:
                payload['users'] = self.serialize(serializers.UserMonthlyTotalSerializer, reporting.get_user_totals(events))
        return Response(payload)


class UsageEventListAPIView(UsageAPIView):
    def get(self, request):
        _, _, _, events = self.report_context()
        paginator = UsagePagination()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(self.serialize(serializers.UsageEventDetailSerializer, page))


class PrivilegedUsageListAPIView(UsageAPIView):
    def get(self, request):
        if not self.can_view_all():
            raise PermissionDenied('This report requires view_all_usage permission.')
        paginator = UsagePagination()
        page = paginator.paginate_queryset(self.get_queryset(), request, view=self)
        return paginator.get_paginated_response(self.serialize(self.serializer_class, page))


class UsageUserListAPIView(PrivilegedUsageListAPIView):
    serializer_class = serializers.UsageUserChoiceSerializer

    def get_queryset(self):
        return get_user_model().objects.filter(usage_events__isnull=False).distinct().order_by('pk')


class ModelPriceListAPIView(PrivilegedUsageListAPIView):
    serializer_class = serializers.ModelPriceSerializer

    def get_queryset(self):
        return ModelPrice.objects.order_by('-effective_from', '-pk')


class TaskPricingListAPIView(PrivilegedUsageListAPIView):
    serializer_class = serializers.TaskPricingSerializer

    def get_queryset(self):
        return TaskPricing.objects.order_by('-effective_from', '-pk')
