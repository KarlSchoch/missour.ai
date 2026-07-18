from rest_framework import serializers
from celery.result import AsyncResult
from django.urls import reverse

from .models import BackgroundJob, Topic, Summary, Tag, Transcript


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
