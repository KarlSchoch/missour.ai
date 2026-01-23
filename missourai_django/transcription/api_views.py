from rest_framework import viewsets

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filterset_fields = ["transcript"]