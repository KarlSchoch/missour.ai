from rest_framework import viewsets, status, serializers
from rest_framework.response import Response

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary, Transcript
from transcription.summary.summary_manager import SummaryManager
from os import environ

summary_manager = SummaryManager(api_key=environ['OPENAI_API_KEY'])

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filterset_fields = ["transcript"]

    def create(self, request, *args, **kwargs):
        print("Hit Summary API POST route")
        print("request")
        print(request.data)
        # 1. Build serializer from request and validate
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Custom Logic
        data = request.data
        try: 
            summary_type = data['summary_type']
            transcript = data['transcript']
        except KeyError as e:
            return Response(
                f"Key used in backend ({e.args[0]}) not found in frontend request",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # Check whether this is a general or topic level summary
            ## General
            if summary_type == 'general':
                print("Summary Type: General")
                pass
                ### Query the DB for the transcript
                tgt_transcript = Transcript.objects.get(pk = int(transcript))
                print(type(tgt_transcript))
                print(tgt_transcript.__dict__.keys())
                ### Extract the text that needs to be summarized
                tgt_text = tgt_transcript.transcript_text
                print("tgt_text", tgt_text[:50])
                ### Call the OpenAI API through the summary manager
                summary = summary_manager.summarize(tgt_text)
                print('summary', summary)
                ### Create a summary object: transcript, summary_type, topic, text
            ## Topic Level
            elif summary_type == 'topic':
                print("Summary Type: Topic Level")
                pass
                ###
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
        except Exception as e:
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )