from rest_framework import viewsets, status, serializers
from rest_framework.response import Response

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary, Transcript

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
            raise TypeError('Some error message')
            summary_type = data['summary_type']
            transcript = data['transcript_id']
        except KeyError as e:
            return Response(
                f"Key used in backend ({e.args[0]}) not found in frontend request",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            print("Inside general exception handler block")
            print(e.args)
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # Check whether this is a general or topic level summary
            ## General
            if summary_type == 'general':
                pass
                ### Query the DB for the transcript
                tgt_transcript = Transcript.filter(pk = int(transcript))
                print(type(tgt_transcript))
                print(tgt_transcript)
                ### Extract the text that needs to be summarized
                ### Call the OpenAI API
                ### Create a summary object: transcript, summary_type, topic, text
            ## Topic Level
            elif summary_type == 'topic':
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
                f"Key used in backend ({e.args[0]}) not found in frontend request",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )