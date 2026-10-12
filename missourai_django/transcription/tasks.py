from celery import shared_task
from celery.exceptions import Ignore
from django.core.files.storage import default_storage
from django.utils import timezone

from transcription.models import BackgroundJob, Topic, Transcript, TranscriptionJobMetric
from transcription.tagging.tagging_manager import TaggingManager
from transcription.transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError,
)
from transcription.transcription_utils.sources import SourceError

import logging
import os
import socket
import time

from transcription.services.transcription_billing import (
    claim_transcription_attempt,
    record_transcript_delivery,
    try_finalize_transcription_billing,
    mark_transcription_not_billable,
)

logger = logging.getLogger(__name__)
GENERIC_TRANSCRIPTION_ERROR = (
    "The uploaded audio could not be processed. Please try another file or contact support."
)
DEFAULT_TRANSCRIPTION_MAX_CONCURRENT_CHUNKS = 1


def get_transcription_max_concurrent_chunks() -> int:
    raw_value = os.getenv("TRANSCRIPTION_MAX_CONCURRENT_CHUNKS")
    if not raw_value:
        logger.info(
            "TRANSCRIPTION_MAX_CONCURRENT_CHUNKS=%s",
            DEFAULT_TRANSCRIPTION_MAX_CONCURRENT_CHUNKS
        )
        return DEFAULT_TRANSCRIPTION_MAX_CONCURRENT_CHUNKS

    try:
        max_concurrent_chunks = max(1, int(raw_value))
        logger.info(
            "TRANSCRIPTION_MAX_CONCURRENT_CHUNKS=%s",
            max_concurrent_chunks
        )
        return max(1, int(raw_value))
    except ValueError:
        logger.warning(
            "Invalid TRANSCRIPTION_MAX_CONCURRENT_CHUNKS=%s; using default=%s",
            raw_value,
            DEFAULT_TRANSCRIPTION_MAX_CONCURRENT_CHUNKS,
        )
        return DEFAULT_TRANSCRIPTION_MAX_CONCURRENT_CHUNKS


def finish_transcription_job_metric(
    job_metric: TranscriptionJobMetric,
    status: str,
    total_duration_sec: float,
    error: Exception | None = None,
):
    job_metric.status = status
    job_metric.finished_at = timezone.now()
    job_metric.total_duration_sec = total_duration_sec
    if error:
        job_metric.error_type = error.__class__.__name__
        job_metric.error_message = str(error)
    job_metric.save(
        update_fields=[
            "status",
            "finished_at",
            "total_duration_sec",
            "error_type",
            "error_message",
        ]
    )

def get_upload_file_size(upload_path: str) -> int | None:
    try:
        return os.path.getsize(upload_path)
    except OSError:
        logger.debug("Could not determine upload file size for %s", upload_path)
        return None


def process_audio(
    file_path: str,
    job_metric: TranscriptionJobMetric | None = None,
    max_concurrent_chunks: int | None = None,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")

    max_concurrent_chunks = (
        max_concurrent_chunks
        if max_concurrent_chunks is not None
        else get_transcription_max_concurrent_chunks()
    )
    started_at = time.perf_counter()
    try:
        manager = TranscriptionManager(
            api_key,
            file_path,
            max_concurrent_chunks=max_concurrent_chunks,
            job_metric=job_metric,
        )
        transcript = manager.create_transcript()
        if job_metric:
            finish_transcription_job_metric(
                job_metric=job_metric,
                status=TranscriptionJobMetric.Status.SUCCESS,
                total_duration_sec=time.perf_counter() - started_at,
            )
        return transcript
    except TranscriptionMediaError as exc:
        if job_metric:
            finish_transcription_job_metric(
                job_metric=job_metric,
                status=TranscriptionJobMetric.Status.FAILED,
                total_duration_sec=time.perf_counter() - started_at,
                error=exc,
            )
        raise
    except Exception as exc:
        logger.exception("Unexpected transcription failure for file %s", file_path)
        if job_metric:
            finish_transcription_job_metric(
                job_metric=job_metric,
                status=TranscriptionJobMetric.Status.FAILED,
                total_duration_sec=time.perf_counter() - started_at,
                error=exc,
            )
        raise RuntimeError(
            "An unexpected error occurred while processing the file."
        ) from exc


@shared_task
def transcribe_uploaded_audio(job_id, upload_storage_name, transcript_id, topic_ids):
    job = BackgroundJob.objects.select_related("created_by").get(id=job_id)
    user = job.created_by
    transcript = Transcript.objects.get(id=transcript_id, created_by=user)
    attempt = claim_transcription_attempt(job, transcript)
    if attempt is None:
        # Duplicate delivery must neither repeat paid work nor delete the
        # upload still being used by the original worker.
        logger.warning("Duplicate transcription task ignored job_id=%s", job_id)
        raise Ignore()
    job_metric = None
    task_started_at = time.perf_counter()

    try:
        upload_path = default_storage.path(upload_storage_name)
        max_concurrent_chunks = get_transcription_max_concurrent_chunks()
        job_metric = TranscriptionJobMetric.objects.create(
            background_job=job,
            transcript=transcript,
            file_size_bytes=get_upload_file_size(upload_path),
            max_concurrent_chunks=max_concurrent_chunks,
            worker_hostname=socket.gethostname(),
        )
        transcript_text = process_audio(
            upload_path,
            job_metric=job_metric,
            max_concurrent_chunks=max_concurrent_chunks,
        )

        selected_topics = list(
            Topic.objects.filter(
                id__in=topic_ids,
                created_by=user,
            )
        )
        if len(selected_topics) != len(topic_ids):
            raise ValueError("One or more selected topics could not be found.")

        record_transcript_delivery(attempt.pk, transcript_text)
        transcript.transcript_text = transcript_text
        try_finalize_transcription_billing(attempt.pk)

        if selected_topics:
            tagging_manager = TaggingManager(
                api_key=os.getenv("OPENAI_API_KEY"),
                transcript=transcript,
                topics=selected_topics,
            )
            tagging_manager.tag_transcript()

        job.error_message = ""
        job.save(update_fields=["error_message"])
        return transcript.id
    except Exception as exc:
        try:
            mark_transcription_not_billable(attempt.pk, exc)
        except Exception:
            logger.exception("Transcription failure cleanup needs recovery attempt_id=%s", attempt.pk)
        if (
            job_metric
            and job_metric.status == TranscriptionJobMetric.Status.RUNNING
        ):
            finish_transcription_job_metric(
                job_metric=job_metric,
                status=TranscriptionJobMetric.Status.FAILED,
                total_duration_sec=time.perf_counter() - task_started_at,
                error=exc,
            )
        logger.exception("Transcription background job failed job_id=%s", job_id)
        job.error_message = GENERIC_TRANSCRIPTION_ERROR
        job.save(update_fields=["error_message"])
        raise
    finally:
        if default_storage.exists(upload_storage_name):
            default_storage.delete(upload_storage_name)


def _tag_selected_topics(transcript, topic_ids):
    selected = list(Topic.objects.filter(id__in=topic_ids, created_by=transcript.created_by))
    if len(selected) != len(set(topic_ids)):
        raise ValueError("One or more selected topics could not be found.")
    if selected:
        TaggingManager(api_key=os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=selected).tag_transcript()


@shared_task
def transcribe_youtube(job_id, transcript_id, topic_ids):
    job = BackgroundJob.objects.select_related("created_by").get(pk=job_id)
    transcript = Transcript.objects.get(pk=transcript_id, created_by=job.created_by, source_type="youtube")
    attempt = claim_transcription_attempt(job, transcript)
    if attempt is None:
        raise Ignore()
    started = time.perf_counter()
    manager = None
    metric = TranscriptionJobMetric.objects.create(background_job=job, transcript=transcript,
        max_concurrent_chunks=get_transcription_max_concurrent_chunks(), worker_hostname=socket.gethostname())

    def progress(stage):
        BackgroundJob.objects.filter(pk=job.pk).update(processing_stage=stage)

    def metadata(info):
        transcript.video_title = (info.get("title") or "")[:500]
        transcript.source_duration_seconds = info["duration"]
        fields = ["video_title", "source_duration_seconds"]
        if transcript.name == transcript.video_id and transcript.video_title:
            transcript.name = transcript.video_title[:255]
            fields.append("name")
        transcript.save(update_fields=fields)
        BackgroundJob.objects.filter(pk=job.pk).update(label=f"Transcribe {transcript.name}")

    try:
        Transcript.objects.filter(pk=transcript.pk).update(source_status="processing")
        manager = TranscriptionManager(api_key=os.getenv("OPENAI_API_KEY"), youtube_url=transcript.source_url,
            job_metric=metric, max_concurrent_chunks=metric.max_concurrent_chunks,
            progress=progress, metadata_callback=metadata)
        result = manager.process_source()
        record_transcript_delivery(attempt.pk, result.text, source_result=result)
        transcript.transcript_text = result.text
        try_finalize_transcription_billing(attempt.pk)
        finish_transcription_job_metric(metric, TranscriptionJobMetric.Status.SUCCESS, time.perf_counter() - started)
        progress("tagging" if topic_ids else "complete")
        _tag_selected_topics(transcript, topic_ids)
        progress("complete")
        return transcript.pk
    except Exception as exc:
        logger.exception("YouTube processing failed job_id=%s", job.pk)
        mark_transcription_not_billable(attempt.pk, exc)
        transcript.refresh_from_db()
        if transcript.source_status != "ready":
            Transcript.objects.filter(pk=transcript.pk).update(source_status="failed",
                retrieval_errors=(manager.retrieval_errors if manager else []) + [str(exc) if isinstance(exc, SourceError)
                    else "Video processing failed. Please retry or contact support."])
            finish_transcription_job_metric(metric, TranscriptionJobMetric.Status.FAILED, time.perf_counter() - started, exc)
        job.error_message = ("Transcript tagging failed. The transcript remains available."
            if transcript.source_status == "ready" else str(exc) if isinstance(exc, SourceError)
            else "Video processing failed. Please retry or contact support.")
        job.processing_stage = "failed"
        job.save(update_fields=["error_message", "processing_stage"])
        raise


@shared_task
def tag_saved_transcript(job_id, transcript_id, topic_ids):
    from django.db import transaction
    job = BackgroundJob.objects.get(pk=job_id)
    # A conditional DB update claims the job even when select_for_update is
    # unavailable (SQLite). Redelivery never repeats tagging calls.
    with transaction.atomic():
        claimed = BackgroundJob.objects.filter(pk=job.pk, processing_stage="pending").update(processing_stage="tagging")
    if not claimed:
        raise Ignore()
    try:
        transcript = Transcript.objects.get(pk=transcript_id, created_by=job.created_by, source_status="ready")
        _tag_selected_topics(transcript, topic_ids)
        BackgroundJob.objects.filter(pk=job.pk).update(processing_stage="complete")
        return transcript.pk
    except Exception:
        BackgroundJob.objects.filter(pk=job.pk).update(processing_stage="failed", error_message="Transcript tagging failed. The transcript remains available.")
        raise
