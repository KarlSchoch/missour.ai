from rest_framework import viewsets

from .serializers import TopicSerializer
from .models import Topic

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer