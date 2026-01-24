from rest_framework import serializers

from .models import Topic, Summary

class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["id", "topic", "description"]

class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        fields = ["transcript", "summary_type", "topic", "text"]

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
