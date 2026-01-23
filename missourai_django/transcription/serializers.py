from .models import Topic, Summary
from rest_framework.serializers import ModelSerializer

class TopicSerializer(ModelSerializer):
    class Meta:
        model = Topic
        fields = ["id", "topic", "description"]

class SummarySerializer(ModelSerializer):
    class Meta:
        model = Summary
        fields = ["transcript", "summary_type", "topic", "text"]