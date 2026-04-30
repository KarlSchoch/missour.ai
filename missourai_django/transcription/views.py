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

logger = logging.getLogger(__name__)


def process_audio(file_path:str) -> str:
    # Intialize TranscriptionManager with OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")
    
    # Create the transcript using the TranscriptionManager
    try:
        manager = TranscriptionManager(api_key, file_path)
        return manager.create_transcript()
    except TranscriptionMediaError:
        raise
    except Exception as exc:
        logging.exception("Unexpected transcription failure for file %s", file_path)
        raise RuntimeError("An unexpected error occurred while processing the file.") from exc

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
        form = TranscriptForm(request.POST, request.FILES)
        if form.is_valid():
            name = form.cleaned_data['name']
            audio_file = form.cleaned_data['audio_file']

            # Extract Selected Topics
            topics_raw = request.POST.get('topics', '[]')
            try:
                selected_topics = json.loads(topics_raw)
            except json.JSONDecodeError:
                selected_topics = []

            # Reuse Django's temp file for large uploads when available.
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
                "Processing upload name=%s file=%s size=%s content_type=%s temp_path=%s reused_temp_file=%s",
                name,
                getattr(audio_file, "name", "<unknown>"),
                getattr(audio_file, "size", "<unknown>"),
                getattr(audio_file, "content_type", "<unknown>"),
                tmp_file_path,
                not remove_tmp_file,
            )
            
            # Generate transcript
            try:
                transcript_text = process_audio(tmp_file_path)
            except TranscriptionMediaError as exc:
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

            selected_topics_ct = len(selected_topics)
            selected_topics = list(
                Topic.objects.filter(topic__in=selected_topics)
            )
            if len(selected_topics) != selected_topics_ct:
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
            transcript_obj.save()

            # Tag the transcript based on selected topics
            try:
                tagging_manager = TaggingManager(
                    api_key = os.getenv('OPENAI_API_KEY'),
                    transcript=transcript_obj,
                    topics = selected_topics
                )
                tagging_manager.tag_transcript()
            except Exception:
                logger.exception(
                    "Tagging failed for transcript_id=%s name=%s",
                    transcript_obj.pk,
                    transcript_obj.name,
                )
                transcript_obj.delete()
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
            return redirect('transcription:transcripts')
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
