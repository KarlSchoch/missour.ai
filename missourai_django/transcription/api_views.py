from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["transcript"]