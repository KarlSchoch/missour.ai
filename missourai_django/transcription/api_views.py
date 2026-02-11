from rest_framework import viewsets, status
from rest_framework.response import Response

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filterset_fields = ["transcript"]

    def create(self, request, *args, **kwargs):
        print("Hit Summary API POST route")
        # 1. Build serializer from request and validate
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Custom Logic
        print(request)
        # 2.a. Send to OpenAI API Endpoint
        # TO DO: Offload as job to celery
        # TO DO: Save all non API call dependent fields

        # 3. Save
        # serializer.save()

        # 4 (???) Custom Logic Post Save

        # 5. Return
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )