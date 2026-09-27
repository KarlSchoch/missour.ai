from rest_framework import serializers
from celery.result import AsyncResult
from celery import states
from django.urls import reverse

from .models import BackgroundJob, Topic, Summary, Tag, Transcript


class BackgroundJobSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    ready = serializers.SerializerMethodField()
    successful = serializers.SerializerMethodField()
    failed = serializers.SerializerMethodField()
    transcript_url = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    transcript_delivered = serializers.SerializerMethodField()
    notification_at = serializers.SerializerMethodField()

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
            "progress",
            "transcript_delivered",
            "notification_at",
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
        # Delivery/failure evidence survives result-backend expiry and is
        # available even before Celery has published its terminal result.
        if obj.kind == BackgroundJob.Kind.TRANSCRIPTION:
            attempt = getattr(obj, "billing_attempt", None)
            metric = getattr(obj, "transcription_metric", None)
            if obj.error_message or (attempt and attempt.processing_state == "failed"):
                return states.FAILURE
            if attempt and attempt.processing_state == "delivered":
                return states.SUCCESS
            if metric and metric.status == "failed":
                return states.FAILURE
        return self._task(obj).status

    def get_ready(self, obj):
        return self.get_status(obj) in states.READY_STATES

    def get_successful(self, obj):
        return self.get_status(obj) == states.SUCCESS

    def get_failed(self, obj):
        return self.get_status(obj) in {states.FAILURE, states.REVOKED}

    def get_transcript_delivered(self, obj):
        attempt = getattr(obj, "billing_attempt", None)
        return bool(attempt and attempt.processing_state == "delivered")

    def get_notification_at(self, obj):
        attempt = getattr(obj, "billing_attempt", None)
        metric = getattr(obj, "transcription_metric", None)
        timestamp = (attempt.delivered_at if attempt else None) or (metric.finished_at if metric else None) or obj.created_at
        return timestamp.isoformat()

    def get_progress(self, obj):
        metric = getattr(obj, "transcription_metric", None)
        if obj.kind != BackgroundJob.Kind.TRANSCRIPTION or metric is None:
            return None
        chunks = list(metric.chunk_metrics.all())
        return {
            "total_chunks": metric.chunk_count,
            "started_chunks": sorted({chunk.chunk_index for chunk in chunks}),
            "active_chunks": sorted({chunk.chunk_index for chunk in chunks if chunk.status == "running"}),
        }

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
