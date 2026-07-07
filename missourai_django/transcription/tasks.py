from celery import shared_task
from django.core.files.storage import default_storage
from django.utils import timezone

from transcription.models import BackgroundJob, Topic, Transcript, TranscriptionJobMetric
from transcription.tagging.tagging_manager import TaggingManager
from transcription.transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError,
)

import logging
import os
import socket
import time

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

    logger.info(
        "transcription_job_completed",
        extra={
            "job_metric_id": job_metric.id,
            "background_job_id": job_metric.background_job_id,
            "transcript_id": job_metric.transcript_id,
            "file_size_bytes": job_metric.file_size_bytes,
            "audio_duration_sec": job_metric.audio_duration_sec,
            "normalized_duration_sec": job_metric.normalized_duration_sec,
            "chunk_count": job_metric.chunk_count,
            "max_concurrent_chunks": job_metric.max_concurrent_chunks,
            "model_name": job_metric.model_name,
            "total_duration_sec": total_duration_sec,
            "status": status,
        },
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

        transcript.transcript_text = transcript_text
        transcript.save(update_fields=["transcript_text"])

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
    except Exception:
        logger.exception("Transcription background job failed job_id=%s", job_id)
        job.error_message = GENERIC_TRANSCRIPTION_ERROR
        job.save(update_fields=["error_message"])
        raise
    finally:
        if default_storage.exists(upload_storage_name):
            default_storage.delete(upload_storage_name)
