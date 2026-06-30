from django.shortcuts import render, redirect
from celery import uuid as celery_uuid
from celery.result import AsyncResult
from django.http import HttpResponse, JsonResponse
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .forms import AddNumbersForm, TranscriptForm
from .models import BackgroundJob, Transcript, Topic
from .tasks import add, transcribe_uploaded_audio
from .tagging.tagging_manager import TaggingManager

import os
import logging
import json
import uuid

logger = logging.getLogger(__name__)


# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

@login_required
def transcripts(request):
    transcripts = Transcript.objects.filter(
        created_by=request.user
    )

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

            selected_topics_ct = len(selected_topics)
            selected_topics = list(
                Topic.objects.filter(
                    topic__in=selected_topics,
                    created_by=request.user,
                )
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

            upload_storage_name = _save_upload_for_background_job(audio_file)
            task_id = celery_uuid()
            job = BackgroundJob.objects.create(
                created_by=request.user,
                task_id=task_id,
                kind=BackgroundJob.Kind.TRANSCRIPTION,
                label=f"Transcribe {name}",
            )

            transcribe_uploaded_audio.apply_async(
                args=[
                    job.id,
                    upload_storage_name,
                    name,
                    [topic.id for topic in selected_topics],
                ],
                task_id=task_id,
            )

            messages.info(
                request,
                "Your audio has been queued for transcription. The result page will check its status.",
            )
            return redirect(
                "transcription:transcription_job_result",
                job_id=job.id,
            )
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})


def _save_upload_for_background_job(audio_file):
    extension = os.path.splitext(audio_file.name)[1]
    storage_name = f"background_uploads/{uuid.uuid4()}{extension}"

    return default_storage.save(storage_name, audio_file)

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    if request.user != transcript.created_by:
        raise PermissionDenied
    
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
            x for x in Topic.objects.filter(
                topic__in=topics_processed,
                created_by=request.user,
            )
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


@login_required
def add_task_submit(request):
    if request.method == "POST":
        form = AddNumbersForm(request.POST)
        if form.is_valid():
            x = form.cleaned_data["x"]
            y = form.cleaned_data["y"]
            task = add.delay(
                x,
                y,
            )
            job = BackgroundJob.objects.create(
                created_by=request.user,
                task_id=task.id,
                kind=BackgroundJob.Kind.ADD_DEMO,
                label=f"Add {x} + {y}",
            )
            messages.info(
                request,
                "Your add task has been queued. The result page will check its status.",
            )
            return redirect(
                "transcription:add_task_result",
                job_id=job.id,
            )
    else:
        form = AddNumbersForm()

    return render(
        request,
        "transcription/add_task_submit.html",
        {"form": form},
    )


@login_required
def add_task_result(request, job_id):
    job = get_object_or_404(
        BackgroundJob,
        id=job_id,
        created_by=request.user,
    )
    task = AsyncResult(job.task_id)

    return render(
        request,
        "transcription/add_task_result.html",
        {
            "job": job,
            "task": task,
            "task_status_url": reverse(
                "transcription:celery_task_status",
                args=[job.task_id],
            ),
        },
    )


@login_required
def transcription_job_result(request, job_id):
    job = get_object_or_404(
        BackgroundJob,
        id=job_id,
        kind=BackgroundJob.Kind.TRANSCRIPTION,
        created_by=request.user,
    )
    task = AsyncResult(job.task_id)
    transcript = None

    if task.successful() and job.related_object_id:
        transcript = get_object_or_404(
            Transcript,
            id=job.related_object_id,
            created_by=request.user,
        )

    return render(
        request,
        "transcription/transcription_job_result.html",
        {
            "job": job,
            "task": task,
            "transcript": transcript,
            "task_status_url": reverse(
                "transcription:celery_task_status",
                args=[job.task_id],
            ),
        },
    )


@login_required
def celery_task_status(request, task_id):
    get_object_or_404(
        BackgroundJob,
        task_id=str(task_id),
        created_by=request.user,
    )
    task = AsyncResult(str(task_id))

    return JsonResponse(
        {
            "task_id": str(task_id),
            "status": task.status,
            "ready": task.ready(),
            "successful": task.successful(),
            "failed": task.failed(),
        }
    )
