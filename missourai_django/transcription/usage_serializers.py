"""Explicit reporting contracts; internal pricing fields require reporting permission."""
from rest_framework import serializers
from .models import ModelPrice, TaskPricing, UsageEvent


class UsageFiltersSerializer(serializers.Serializer):
    month = serializers.RegexField(r'^[0-9]{4}-[0-9]{2}$', required=False)
    user_id = serializers.IntegerField(min_value=1, required=False)
    task_type = serializers.ChoiceField(choices=TaskPricing.TaskType.choices, required=False)
    model_name = serializers.CharField(max_length=100, required=False)
    status = serializers.ChoiceField(choices=UsageEvent.Status.choices, required=False)


class InternalFieldsMixin:
    internal_fields = ('base_cost',)

    def get_fields(self):
        fields = super().get_fields()
        if not self.context.get('can_view_all_usage', False):
            for name in self.internal_fields:
                fields.pop(name, None)
        return fields


class OverallMonthlyTotalSerializer(InternalFieldsMixin, serializers.Serializer):
    currency = serializers.CharField()
    event_count = serializers.IntegerField()
    base_cost = serializers.DecimalField(max_digits=30, decimal_places=10)
    billed_cost = serializers.DecimalField(max_digits=30, decimal_places=10)


class MonthlyTaskTotalSerializer(OverallMonthlyTotalSerializer):
    task_type = serializers.CharField()


class UserMonthlyTotalSerializer(OverallMonthlyTotalSerializer):
    user_id = serializers.IntegerField()


class AppliedPricingPeriodSerializer(MonthlyTaskTotalSerializer):
    provider = serializers.CharField()
    model_name = serializers.CharField()
    billing_unit = serializers.CharField()
    model_price_id = serializers.IntegerField()
    task_pricing_id = serializers.IntegerField()
    multiplier = serializers.DecimalField(max_digits=12, decimal_places=6)
    model_price_effective_from = serializers.DateTimeField(source='model_price__effective_from')
    model_price_effective_to = serializers.DateTimeField(source='model_price__effective_to', allow_null=True)
    task_pricing_effective_from = serializers.DateTimeField(source='task_pricing__effective_from')
    task_pricing_effective_to = serializers.DateTimeField(source='task_pricing__effective_to', allow_null=True)
    input_rate_per_million = serializers.DecimalField(source='model_price__input_rate_per_million', max_digits=20, decimal_places=10, allow_null=True)
    cached_input_rate_per_million = serializers.DecimalField(source='model_price__cached_input_rate_per_million', max_digits=20, decimal_places=10, allow_null=True)
    output_rate_per_million = serializers.DecimalField(source='model_price__output_rate_per_million', max_digits=20, decimal_places=10, allow_null=True)
    rate_per_minute = serializers.DecimalField(source='model_price__rate_per_minute', max_digits=20, decimal_places=10, allow_null=True)


class UsageEventDetailSerializer(InternalFieldsMixin, serializers.ModelSerializer):
    internal_fields = ('base_cost', 'multiplier', 'model_price_id', 'task_pricing_id', 'provider_request_id')

    class Meta:
        model = UsageEvent
        fields = (
            'id', 'user_id', 'task_type', 'provider', 'model_name', 'occurred_at',
            'status', 'billing_unit', 'usage_source', 'input_tokens',
            'cached_input_tokens', 'output_tokens', 'audio_duration_seconds',
            'base_cost', 'multiplier', 'billed_cost', 'currency', 'model_price_id',
            'task_pricing_id', 'provider_request_id', 'transcript_id', 'summary_id',
            'tag_id', 'transcription_chunk_id',
        )


class UsageUserChoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField(source='get_username')


class ModelPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelPrice
        fields = ('id', 'provider', 'model_name', 'billing_unit', 'currency',
                  'input_rate_per_million', 'cached_input_rate_per_million',
                  'output_rate_per_million', 'rate_per_minute', 'effective_from',
                  'effective_to', 'created_by_id', 'created_at')


class TaskPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPricing
        fields = ('id', 'task_type', 'model_price_id', 'multiplier',
                  'effective_from', 'effective_to', 'created_by_id', 'created_at')
