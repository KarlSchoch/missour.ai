from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .forms import TranscriptForm
from .models import Transcript, Topic
from .transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError
)
from .tagging.tagging_manager import TaggingManager

import os
import logging
import json
import tempfile
import time
import uuid

logger = logging.getLogger(__name__)


def _elapsed_ms(start_time: float) -> int:
    return round((time.monotonic() - start_time) * 1000)


def process_audio(file_path: str, upload_id: str = "<unknown>") -> str:
    process_started = time.monotonic()

    # Intialize TranscriptionManager with OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")
    
    # Create the transcript using the TranscriptionManager
    try:
        manager_started = time.monotonic()
        manager = TranscriptionManager(api_key, file_path)
        logger.info(
            "upload_timing event=transcription_manager_init upload_id=%s elapsed_ms=%s",
            upload_id,
            _elapsed_ms(manager_started),
        )

        transcript_started = time.monotonic()
        transcript = manager.create_transcript()
        logger.info(
            "upload_timing event=create_transcript upload_id=%s elapsed_ms=%s",
            upload_id,
            _elapsed_ms(transcript_started),
        )
        return transcript
    except TranscriptionMediaError:
        raise
    except Exception as exc:
        logging.exception("Unexpected transcription failure for file %s", file_path)
        raise RuntimeError("An unexpected error occurred while processing the file.") from exc
    finally:
        logger.info(
            "upload_timing event=process_audio_total upload_id=%s elapsed_ms=%s",
            upload_id,
            _elapsed_ms(process_started),
        )

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

@login_required
def transcripts(request):
    transcripts = Transcript.objects.all()

    return render(
        request,
        'transcription/transcripts.html',
        {'transcripts': transcripts}
    )

@login_required
def upload_audio(request):
    if request.method == 'POST':
        upload_started = time.monotonic()
        upload_id = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12]
        logger.info(
            "upload_timing event=view_start upload_id=%s method=%s path=%s content_length=%s content_type=%s",
            upload_id,
            request.method,
            request.path,
            request.META.get("CONTENT_LENGTH", "<unknown>"),
            request.META.get("CONTENT_TYPE", "<unknown>"),
        )

        form_started = time.monotonic()
        form = TranscriptForm(request.POST, request.FILES)
        form_is_valid = form.is_valid()
        logger.info(
            "upload_timing event=form_parse_validate upload_id=%s elapsed_ms=%s valid=%s",
            upload_id,
            _elapsed_ms(form_started),
            form_is_valid,
        )

        if form_is_valid:
            name = form.cleaned_data['name']
            audio_file = form.cleaned_data['audio_file']

            # Extract Selected Topics
            topics_started = time.monotonic()
            topics_raw = request.POST.get('topics', '[]')
            try:
                selected_topics = json.loads(topics_raw)
            except json.JSONDecodeError:
                selected_topics = []
            logger.info(
                "upload_timing event=parse_topics upload_id=%s elapsed_ms=%s selected_topic_count=%s",
                upload_id,
                _elapsed_ms(topics_started),
                len(selected_topics),
            )

            # Reuse Django's temp file for large uploads when available.
            temp_file_started = time.monotonic()
            remove_tmp_file = False
            if hasattr(audio_file, "temporary_file_path"):
                tmp_file_path = audio_file.temporary_file_path()
            else:
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=os.path.splitext(audio_file.name)[1]
                ) as tmp_file:
                    for chunk in audio_file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name
                remove_tmp_file = True

            logger.info(
                "upload_timing event=temp_file_ready upload_id=%s elapsed_ms=%s name=%s file=%s size=%s content_type=%s temp_path=%s reused_temp_file=%s",
                upload_id,
                _elapsed_ms(temp_file_started),
                name,
                getattr(audio_file, "name", "<unknown>"),
                getattr(audio_file, "size", "<unknown>"),
                getattr(audio_file, "content_type", "<unknown>"),
                tmp_file_path,
                not remove_tmp_file,
            )
            
            # Generate transcript
            try:
                transcription_started = time.monotonic()
                transcript_text = process_audio(tmp_file_path, upload_id=upload_id)
                logger.info(
                    "upload_timing event=process_audio_view_call upload_id=%s elapsed_ms=%s",
                    upload_id,
                    _elapsed_ms(transcription_started),
                )
            except TranscriptionMediaError as exc:
                logger.info(
                    "upload_timing event=view_return upload_id=%s status=400 elapsed_ms=%s",
                    upload_id,
                    _elapsed_ms(upload_started),
                )
                form.add_error("audio_file", str(exc))
                return render(
                    request,
                    "transcription/upload_audio.html",
                    {"form": form},
                    status=400,
                )
            except (RuntimeError, ValueError):
                logger.exception(
                    "Transcription failed for upload name=%s file=%s",
                    name,
                    getattr(audio_file, "name", "<unknown>"),
                )
                logger.info(
                    "upload_timing event=view_return upload_id=%s status=500 elapsed_ms=%s",
                    upload_id,
                    _elapsed_ms(upload_started),
                )
                form.add_error(
                    None,
                    "Something went wrong while transcribing the uploaded file.",
                )
                return render(
                    request,
                    "transcription/upload_audio.html",
                    {"form": form},
                    status=500,
                )
            finally:
                if remove_tmp_file and os.path.exists(tmp_file_path):
                    os.remove(tmp_file_path)

            topic_query_started = time.monotonic()
            selected_topics_ct = len(selected_topics)
            selected_topics = list(
                Topic.objects.filter(topic__in=selected_topics)
            )
            logger.info(
                "upload_timing event=topic_query upload_id=%s elapsed_ms=%s requested_topic_count=%s matched_topic_count=%s",
                upload_id,
                _elapsed_ms(topic_query_started),
                selected_topics_ct,
                len(selected_topics),
            )
            if len(selected_topics) != selected_topics_ct:
                logger.info(
                    "upload_timing event=view_return upload_id=%s status=400 elapsed_ms=%s",
                    upload_id,
                    _elapsed_ms(upload_started),
                )
                form.add_error(
                    None,
                    "One or more selected topics could not be found.",
                )
                return render(
                    request,
                    "transcription/upload_audio.html",
                    {"form": form},
                    status=400,
                )

            # Save the transcript text
            transcript_obj = Transcript(
                name=name,
                transcript_text=transcript_text,
            )
            transcript_save_started = time.monotonic()
            transcript_obj.save()
            logger.info(
                "upload_timing event=transcript_save upload_id=%s elapsed_ms=%s transcript_id=%s",
                upload_id,
                _elapsed_ms(transcript_save_started),
                transcript_obj.pk,
            )

            # Tag the transcript based on selected topics
            try:
                tagging_started = time.monotonic()
                tagging_manager = TaggingManager(
                    api_key = os.getenv('OPENAI_API_KEY'),
                    transcript=transcript_obj,
                    topics = selected_topics
                )
                tagging_manager.tag_transcript()
                logger.info(
                    "upload_timing event=tag_transcript upload_id=%s elapsed_ms=%s transcript_id=%s",
                    upload_id,
                    _elapsed_ms(tagging_started),
                    transcript_obj.pk,
                )
            except Exception:
                logger.exception(
                    "Tagging failed for transcript_id=%s name=%s",
                    transcript_obj.pk,
                    transcript_obj.name,
                )
                transcript_obj.delete()
                logger.info(
                    "upload_timing event=view_return upload_id=%s status=500 elapsed_ms=%s",
                    upload_id,
                    _elapsed_ms(upload_started),
                )
                form.add_error(
                    None,
                    "Something went wrong while tagging the transcript.",
                )
                return render(
                    request,
                    "transcription/upload_audio.html",
                    {"form": form},
                    status=500,
                )

            # Redirect to transcripts page
            logger.info(
                "upload_timing event=view_return upload_id=%s status=302 elapsed_ms=%s",
                upload_id,
                _elapsed_ms(upload_started),
            )
            return redirect('transcription:transcripts')
        logger.info(
            "upload_timing event=view_return upload_id=%s status=200 form_valid=false elapsed_ms=%s",
            upload_id,
            _elapsed_ms(upload_started),
        )
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    if request.method == 'POST':
        # 1. Pull the tags out of the frontned
        topics_raw = request.POST.get('topics', '[]')
        try:
            topics_processed = json.loads(topics_raw)
        except json.JSONDecodeError:
            topics_processed = []
        # 2. TO DO: Conduct Data Validation
        # validate that you aren't getting an empty list of topics
        # if len(topics_processed) == 0:
        #     print("Please select valid topics")
        # Validate that you aren't getting duplicate topics
        # validate all your topics match 1:1 with topics in the DB

        # 3. Translate topics_processed into list[Topic]
        selected_topics = [
            x for x in Topic.objects.filter(topic__in=topics_processed)
        ]

        # 4. Tag the transcript based on selected topics
        tagging_manager = TaggingManager(
            api_key = os.getenv('OPENAI_API_KEY'),
            transcript = transcript,
            topics = selected_topics
        )
        tags = tagging_manager.tag_transcript()

        return render(
            request,
            'transcription/view_transcript.html',
            {'transcript': transcript}
        )

    return render(request, 'transcription/view_transcript.html', {'transcript': transcript})

@login_required
def view_topics(request):
    payload = {
        "apiUrls": {
            "topics": reverse("api:topic-list")
        }
    }

    return render(
        request, "transcription/view_topics.html", 
        {"initial_payload": payload}
    )

@login_required
def analyze_audio_page_section(request):

    return render(
        request,
        "transcription/partials/analyze-audio-page-section.html",
    )

@login_required
def generate_report_page_section(request):
    return render(
        request,
        "transcription/partials/generate-report-page-section.html",
    )
