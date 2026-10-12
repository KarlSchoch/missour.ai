from django.shortcuts import render, redirect
from celery import uuid as celery_uuid
from celery.result import AsyncResult
from django.http import HttpResponse, JsonResponse
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from .forms import TranscriptForm, YouTubeForm
from .models import BackgroundJob, Transcript, Topic, TranscriptionBillingAttempt
from .tasks import transcribe_uploaded_audio, transcribe_youtube, tag_saved_transcript
from .tagging.tagging_manager import TaggingManager

import os
import logging
import json
import uuid

logger = logging.getLogger(__name__)
TRANSCRIPTION_PENDING_TEXT = ""


@login_required
def usage(request):
    payload = {
        'apiUrls': {
            key: reverse('api:' + name)
            for key, name in {
                'summary': 'usage-summary', 'events': 'usage-events',
                'users': 'usage-users', 'modelPrices': 'usage-model-prices',
                'taskPricing': 'usage-task-pricing',
                'pricingReadiness': 'usage-pricing-readiness',
                'pricingModelOptions': 'usage-pricing-model-options',
            }.items()
        },
        'capabilities': {
            'canViewAllUsage': request.user.has_perm('transcription.view_all_usage'),
            'canManagePricing': request.user.has_perm('transcription.manage_usage_pricing'),
        },
        'defaults': {'currency': 'USD', 'timezone': 'UTC'},
    }
    return render(request, 'transcription/usage.html', {'initial_payload': payload})


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
        form_is_valid = form.is_valid()

        if form_is_valid:
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
            transcript = Transcript.objects.create(
                name=name,
                transcript_text="",
                created_by=request.user,
            )
            task_id = celery_uuid()
            job = BackgroundJob.objects.create(
                created_by=request.user,
                task_id=task_id,
                kind=BackgroundJob.Kind.TRANSCRIPTION,
                label=f"Transcribe {name}",
                related_object_id=transcript.id,
            )

            TranscriptionBillingAttempt.objects.create(background_job=job, transcript=transcript)
            transcribe_uploaded_audio.apply_async(
                args=[
                    job.id,
                    upload_storage_name,
                    transcript.id,
                    [topic.id for topic in selected_topics],
                ],
                task_id=task_id,
            )

            return redirect(
                "transcription:view_transcript",
                transcript_id=transcript.id,
            )
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})


def _save_upload_for_background_job(audio_file):
    extension = os.path.splitext(audio_file.name)[1]
    storage_name = f"background_uploads/{uuid.uuid4()}{extension}"

    return default_storage.save(storage_name, audio_file)


def _enqueue_youtube_job(task, job, transcript, topic_ids):
    try:
        task.apply_async(args=[job.pk, transcript.pk, topic_ids], task_id=job.task_id)
    except Exception:
        # A broker failure is visible and explicitly retryable, never a stuck
        # pending transcript that silently blocks subsequent submissions.
        logger.exception("Could not enqueue video job %s", job.pk)
        BackgroundJob.objects.filter(pk=job.pk).update(error_message="Could not start processing. Please retry.", processing_stage="failed")
        if job.kind == BackgroundJob.Kind.TRANSCRIPTION:
            from .services.transcription_billing import mark_transcription_not_billable
            attempt = TranscriptionBillingAttempt.objects.get(background_job=job)
            mark_transcription_not_billable(attempt.pk, "Could not enqueue processing.")
            Transcript.objects.filter(pk=transcript.pk).update(source_status="failed")


def _queue_saved_tagging(transcript, topic_ids):
    if not topic_ids:
        return True
    with transaction.atomic():
        Transcript.objects.select_for_update().get(pk=transcript.pk)
        if BackgroundJob.objects.filter(created_by=transcript.created_by, related_object_id=transcript.pk,
                kind__in=[BackgroundJob.Kind.TRANSCRIPTION, BackgroundJob.Kind.TAGGING]).exclude(
                    processing_stage__in=["complete", "failed"]).exists():
            return False
        job = BackgroundJob.objects.create(created_by=transcript.created_by, task_id=celery_uuid(),
            kind=BackgroundJob.Kind.TAGGING, label=f"Tag {transcript.name}",
            related_object_id=transcript.pk, processing_stage="pending")
        transaction.on_commit(lambda: _enqueue_youtube_job(tag_saved_transcript, job, transcript, topic_ids))
    return True


@login_required
def submit_youtube(request):
    form = YouTubeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            names = json.loads(request.POST.get("topics", "[]"))
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise ValueError
            names = list(dict.fromkeys(names))
        except (ValueError, TypeError):
            form.add_error(None, "Please select valid topics.")
            return render(request, "transcription/submit_youtube.html", {"form": form}, status=400)
        topics = list(Topic.objects.filter(topic__in=names, created_by=request.user))
        if len(topics) != len(names):
            form.add_error(None, "One or more selected topics could not be found.")
            return render(request, "transcription/submit_youtube.html", {"form": form}, status=400)
        topic_ids = [topic.pk for topic in topics]
        with transaction.atomic():
            transcript, created = Transcript.objects.get_or_create(
                created_by=request.user, video_id=form.video_id, source_type="youtube",
                defaults={"name": form.cleaned_data["name"] or form.video_id,
                          "source_url": form.cleaned_data["youtube_url"], "requested_topic_ids": topic_ids})
            start = created
            if not created and transcript.source_status == "failed":
                if not form.cleaned_data["retry"]:
                    form.add_error(None, "Previous processing failed. Open the transcript to retry explicitly.")
                else:
                    start = bool(Transcript.objects.filter(pk=transcript.pk, source_status="failed").update(source_status="pending"))
                    if "topics" not in request.POST:
                        topic_ids = list(Topic.objects.filter(pk__in=transcript.requested_topic_ids,
                            created_by=request.user).values_list("pk", flat=True))
                    if start:
                        Transcript.objects.filter(pk=transcript.pk).update(requested_topic_ids=topic_ids)
            if start:
                job = BackgroundJob.objects.create(created_by=request.user, task_id=celery_uuid(),
                    kind=BackgroundJob.Kind.TRANSCRIPTION, label=f"Transcribe {transcript.name}",
                    related_object_id=transcript.pk, processing_stage="pending")
                TranscriptionBillingAttempt.objects.create(background_job=job, transcript=transcript)
                transaction.on_commit(lambda: _enqueue_youtube_job(transcribe_youtube, job, transcript, topic_ids))
            elif transcript.source_status == "ready" and topics:
                if not _queue_saved_tagging(transcript, topic_ids):
                    form.add_error(None, "Tagging is already in progress. Please select additional topics after it completes.")
        if not form.errors:
            return redirect("transcription:view_transcript", transcript_id=transcript.pk)
    return render(request, "transcription/submit_youtube.html", {"form": form}, status=400 if form.errors else 200)

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    if request.user != transcript.created_by:
        raise PermissionDenied

    if request.method == 'POST' and transcript.source_type == 'youtube':
        if transcript.source_status != 'ready':
            return HttpResponse("Please wait for a completed transcript before selecting topics.", status=409)
        try:
            names = json.loads(request.POST.get('topics', '[]'))
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise ValueError
            names = list(dict.fromkeys(names))
        except (ValueError, TypeError):
            return HttpResponse("Please select valid topics.", status=400)
        topics = list(Topic.objects.filter(topic__in=names, created_by=request.user))
        if len(topics) != len(names):
            return HttpResponse("One or more selected topics could not be found.", status=400)
        if not _queue_saved_tagging(transcript, [topic.pk for topic in topics]):
            return HttpResponse("Tagging is already in progress. Please select additional topics after it completes.", status=409)
        return redirect('transcription:view_transcript', transcript_id=transcript.pk)
    
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

