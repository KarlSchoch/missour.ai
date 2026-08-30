from rest_framework import serializers
from celery.result import AsyncResult
from django.urls import reverse

from .models import (
    BackgroundJob,
    ModelPrice,
    Summary,
    Tag,
    TaskPricing,
    Topic,
    Transcript,
    UsageEvent,
)


class BackgroundJobSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    ready = serializers.SerializerMethodField()
    successful = serializers.SerializerMethodField()
    failed = serializers.SerializerMethodField()
    transcript_url = serializers.SerializerMethodField()

    class Meta:
        model = BackgroundJob
        fields = [
            "id",
            "kind",
            "label",
            "related_object_id",
            "task_id",
            "status",
            "ready",
            "successful",
            "failed",
            "error_message",
            "created_at",
            "transcript_url",
        ]

    def _task(self, obj):
        cache = getattr(self, "_task_cache", None)
        if cache is None:
            cache = {}
            self._task_cache = cache
        if obj.task_id not in cache:
            cache[obj.task_id] = AsyncResult(obj.task_id)
        return cache[obj.task_id]

    def get_status(self, obj):
        return self._task(obj).status

    def get_ready(self, obj):
        return self._task(obj).ready()

    def get_successful(self, obj):
        return self._task(obj).successful()

    def get_failed(self, obj):
        return self._task(obj).failed()

    def get_transcript_url(self, obj):
        if (
            obj.kind != BackgroundJob.Kind.TRANSCRIPTION
            or not obj.related_object_id
        ):
            return None

        request = self.context.get("request")
        path = reverse(
            "transcription:view_transcript",
            args=[obj.related_object_id],
        )
        return request.build_absolute_uri(path) if request else path

class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["id", "topic", "description"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = [
            "id",
            "topic",
            "chunk",
            "topic_present",
            "relevant_section",
            "user_validation",
        ]

class SummarySerializer(serializers.ModelSerializer):
    transcript = serializers.PrimaryKeyRelatedField(
        queryset=Transcript.objects.none()
    )
    topic = serializers.PrimaryKeyRelatedField(
        queryset=Topic.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Summary
        fields = ["transcript", "summary_type", "topic", "text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["transcript"].queryset = Transcript.objects.filter(
                created_by=request.user
            )
            self.fields["topic"].queryset = Topic.objects.filter(
                created_by=request.user
            )

    def validate(self, attrs):
        summary_type = attrs.get(
            "summary_type",
            getattr(self.instance, "summary_type", None),
        )
        topic = attrs.get("topic", getattr(self.instance, "topic", None))

        if summary_type == Summary.SummaryType.GENERAL and topic is not None:
            raise serializers.ValidationError(
                {"topic": "Topic must be null when summary_type is general."}
            )
        if summary_type == Summary.SummaryType.TOPIC and topic is None:
            raise serializers.ValidationError(
                {"topic": "Topic is required when summary_type is topic."}
            )

        return attrs


class InternalCostFieldsMixin:
    internal_cost_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get("include_internal_costs", False):
            for field_name in self.internal_cost_fields:
                self.fields.pop(field_name, None)


class UsageCostTotalsSerializer(InternalCostFieldsMixin, serializers.Serializer):
    internal_cost_fields = ("base_cost",)
    event_count = serializers.IntegerField()
    base_cost = serializers.DecimalField(max_digits=20, decimal_places=10)
    billed_cost = serializers.DecimalField(max_digits=20, decimal_places=10)


class MonthlyTaskTotalSerializer(UsageCostTotalsSerializer):
    task_type = serializers.ChoiceField(choices=TaskPricing.TaskType.choices)


class UserMonthlyTotalSerializer(UsageCostTotalsSerializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField(source="user__username")


class OverallMonthlyTotalSerializer(UsageCostTotalsSerializer):
    pass


class UsageStatusCountSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UsageEvent.Status.choices)
    event_count = serializers.IntegerField()


class AppliedPricingPeriodSerializer(UsageCostTotalsSerializer):
    internal_cost_fields = ()
    task_type = serializers.ChoiceField(choices=TaskPricing.TaskType.choices)
    provider = serializers.CharField()
    model_name = serializers.CharField()
    billing_unit = serializers.ChoiceField(choices=ModelPrice.BillingUnit.choices)
    currency = serializers.CharField()
    model_price_id = serializers.IntegerField()
    model_price_effective_from = serializers.DateTimeField(
        source="model_price__effective_from"
    )
    model_price_effective_to = serializers.DateTimeField(
        source="model_price__effective_to", allow_null=True
    )
    input_rate_per_million = serializers.DecimalField(
        source="model_price__input_rate_per_million",
        max_digits=20,
        decimal_places=10,
        allow_null=True,
    )
    cached_input_rate_per_million = serializers.DecimalField(
        source="model_price__cached_input_rate_per_million",
        max_digits=20,
        decimal_places=10,
        allow_null=True,
    )
    output_rate_per_million = serializers.DecimalField(
        source="model_price__output_rate_per_million",
        max_digits=20,
        decimal_places=10,
        allow_null=True,
    )
    rate_per_minute = serializers.DecimalField(
        source="model_price__rate_per_minute",
        max_digits=20,
        decimal_places=10,
        allow_null=True,
    )
    task_pricing_id = serializers.IntegerField()
    task_pricing_effective_from = serializers.DateTimeField(
        source="task_pricing__effective_from"
    )
    task_pricing_effective_to = serializers.DateTimeField(
        source="task_pricing__effective_to", allow_null=True
    )
    multiplier = serializers.DecimalField(max_digits=12, decimal_places=6)


class UsageEventDetailSerializer(InternalCostFieldsMixin, serializers.ModelSerializer):
    internal_cost_fields = (
        "base_cost",
        "multiplier",
        "model_price_id",
        "task_pricing_id",
    )
    username = serializers.CharField(source="user.get_username", read_only=True)

    class Meta:
        model = UsageEvent
        fields = [
            "id",
            "user_id",
            "username",
            "task_type",
            "provider",
            "model_name",
            "occurred_at",
            "status",
            "billing_unit",
            "usage_source",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "audio_duration_seconds",
            "base_cost",
            "multiplier",
            "billed_cost",
            "currency",
            "provider_request_id",
            "model_price_id",
            "task_pricing_id",
            "transcript_id",
            "summary_id",
            "tag_id",
            "transcription_chunk_id",
        ]


class UsageUserChoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class ModelPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelPrice
        fields = [
            "id",
            "provider",
            "model_name",
            "billing_unit",
            "input_rate_per_million",
            "cached_input_rate_per_million",
            "output_rate_per_million",
            "rate_per_minute",
            "currency",
            "effective_from",
            "effective_to",
            "created_by_id",
            "created_at",
        ]


class TaskPricingSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="model_price.provider", read_only=True)
    model_name = serializers.CharField(source="model_price.model_name", read_only=True)
    currency = serializers.CharField(source="model_price.currency", read_only=True)

    class Meta:
        model = TaskPricing
        fields = [
            "id",
            "task_type",
            "model_price_id",
            "provider",
            "model_name",
            "currency",
            "multiplier",
            "effective_from",
            "effective_to",
            "created_by_id",
            "created_at",
        ]
