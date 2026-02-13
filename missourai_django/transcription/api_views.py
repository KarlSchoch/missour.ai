from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from os import environ

from .serializers import TopicSerializer, SummarySerializer
from .models import Topic, Summary, Transcript, Tag
from transcription.summary.summary_manager import SummaryManager
from transcription.tagging.tagging_manager import TaggingManager

summary_manager = SummaryManager(api_key=environ['OPENAI_API_KEY'])

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()

    def create():
        pass
    def perform_create(self, serializer):
        return super().perform_create(serializer)

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
        # Extract data from request for downstream processing
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
            # Query the DB for the transcript
            tgt_transcript = Transcript.objects.get(pk = int(transcript))
            # Check whether this is a general or topic level summary
            ## General
            if summary_type == 'general':
                print("Summary Type: General")
                print(type(tgt_transcript))
                print(tgt_transcript.__dict__.keys())
                ### Extract the text that needs to be summarized
                tgt_text = tgt_transcript.transcript_text
                print("tgt_text", tgt_text[:50])
                ### Call the OpenAI API through the summary manager
                summary_text = summary_manager.summarize(tgt_text)
                print('summary_text', summary_text)
                ### Create a summary object: transcript, summary_type, topic, text
            ## Topic Level
            elif summary_type == 'topic':
                print("Summary Type: Topic Level")
                # 1. Through Chunk query the tags for a given transcript (transcript_tags)
                transcript_tags = Tag.objects.filter(chunk__transcript_id = transcript).select_related('topic', 'chunk')
                print("transcript_tags", transcript_tags)
                # 2. Extract the set of topics tags have been generated for (generated_tag_topics)
                generated_tag_topics = set(
                    transcript_tags.values_list("topic_id", flat=True)
                )
                print("generated_tag_topics", generated_tag_topics)
                # 3. Compare generated_tags against the topic passed
                topic = data['topic']
                # 3.a. Topic passed back not in generated_tags
                if int(topic) not in generated_tag_topics:
                    print("Tags not generated for this topic.  Generating")
                    # 3.a.i.  Generate tags for that topic
                    ## Extract the topic
                    tgt_topic_obj = Topic.objects.get(pk = int())
                    ## Instantiate the tagging manager
                    tagging_manager = TaggingManager(
                        api_key=environ['OPENAI_API_KEY'],
                        transcript=tgt_transcript,
                        topics=[tgt_topic_obj]
                    )
                    new_transcript_tags = tagging_manager.tag_transcript()
                    # 3.a.ii. Requery transcript_tags
                # 3.b. Topic passed back in generated_tags
                else:
                    # 3.b.i.  Pass
                    print("Tags already generated for this topic")
                    pass
                
                # 4. Filter tags to only where topic_present field == True
                # 5. Create prompt based on Chunk's chunk_text field
                # 6. Pass prompt to the Summary Manager
                # summary = summary_manager.summarize(tgt_text)
                # 7. Create a summary 
            # TO DO: Offload as job to celery
            # TO DO: Save all non API call dependent fields

            # 3. Save
            # Create a summary entry based on the summary_text
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