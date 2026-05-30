from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from django.shortcuts import get_object_or_404
from os import environ

from .serializers import TopicSerializer, SummarySerializer, TagSerializer
from .models import Topic, Summary, Transcript, Tag
from transcription.summary.summary_manager import SummaryManager
from transcription.tagging.tagging_manager import TaggingManager

summary_manager = SummaryManager(api_key=environ['OPENAI_API_KEY'])

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

    def get_queryset(self):
        return Topic.objects.filter(created_by = self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(created_by = self.request.user)

class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.none()
    serializer_class = TagSerializer

    def get_queryset(self):
        return Tag.objects.filter(
            chunk__transcript__created_by=self.request.user,
            topic__created_by=self.request.user,
        )

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filterset_fields = ["transcript"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Summary.objects.filter(transcript__created_by=self.request.user)

    def create(self, request, *args, **kwargs):
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
            tgt_transcript = get_object_or_404(
                Transcript,
                pk=int(transcript),
                created_by=request.user,
            )
            # Check whether this is a general or topic level summary
            ## General
            if summary_type == 'general':
                ### Extract the text that needs to be summarized
                tgt_text = tgt_transcript.transcript_text
                ### Call the OpenAI API through the summary manager
                summary_obj = summary_manager.summarize(
                    transcript_content=tgt_text,
                    tgt_transcript=tgt_transcript
                )
                ### Create a summary object: transcript, summary_type, topic, text
            ## Topic Level
            elif summary_type == 'topic':
                # 1. Through Chunk query the tags for a given transcript (transcript_tags)
                transcript_tags = Tag.objects.filter(
                    chunk__transcript=tgt_transcript,
                    topic__created_by=request.user,
                ).select_related('topic', 'chunk')
                # 2. Extract the set of topics tags have been generated for (generated_tag_topics)
                generated_tag_topics = set(
                    transcript_tags.values_list("topic_id", flat=True)
                )
                # 3. Compare generated_tags against the topic passed
                topic = data['topic']
                tgt_topic_obj = get_object_or_404(
                    Topic,
                    pk=int(topic),
                    created_by=request.user,
                )
                # 3.a. Topic passed back not in generated_tags
                if tgt_topic_obj.pk not in generated_tag_topics:
                    # 3.a.i.  Generate tags for that topic
                    ## Instantiate the tagging manager
                    tagging_manager = TaggingManager(
                        api_key=environ['OPENAI_API_KEY'],
                        transcript=tgt_transcript,
                        topics=[tgt_topic_obj]
                    )
                    new_transcript_tags = tagging_manager.tag_transcript()
                    # 3.a.ii. Requery transcript_tags
                    transcript_tags = Tag.objects.filter(chunk__transcript=tgt_transcript).select_related('topic', 'chunk')
                # 3.b. Topic passed back in generated_tags
                else:
                    # 3.b.i.  Pass
                    pass
                # 4. Filter tags to only where topic_present field == True that are for the tgt_topic
                transcript_tags = transcript_tags.filter(
                    topic=tgt_topic_obj,
                    topic_present = True
                )
                # Save summary and return if there are no relevant tags for the topic
                if len(transcript_tags) == 0:
                    summary_obj = Summary(
                        transcript=tgt_transcript,
                        summary_type='topic',
                        topic=tgt_topic_obj,
                        text='No content related to this topic in the transcript.'
                    )
                    summary_obj.save()
                    serializer = SummarySerializer(summary_obj)
                    headers = self.get_success_headers(serializer.data)
                    return Response(
                        serializer.data, status=status.HTTP_201_CREATED, headers=headers
                    )        
                # 5. Create prompt based on Chunk's chunk_text field
                transcript_content = transcript_tags.values_list(
                    "chunk__chunk_text",
                    flat=True
                )
                # 6. Pass prompt to the Summary Manager (saves summary in db)
                summary_obj = summary_manager.summarize(
                    transcript_content=transcript_content,
                    tgt_transcript=tgt_transcript,
                    tgt_topic=tgt_topic_obj,
                )

            # TO DO: Offload as job to celery
            # TO DO: Save all non API call dependent fields

            # 3. Save HANDLED IN summary_manager.py
            # Create a summary entry based on the summary_text
            # serializer.save()

            # 4 (???) Custom Logic Post Save

            # 5. Return
            serializer = SummarySerializer(summary_obj)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        except Http404:
            raise
        except Exception as e:
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
