from rest_framework import serializers

from .models import Topic, Summary, Tag, Transcript

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
