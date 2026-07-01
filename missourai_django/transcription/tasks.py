from celery import shared_task
from django.core.files.storage import default_storage

from transcription.models import BackgroundJob, Topic, Transcript
from transcription.tagging.tagging_manager import TaggingManager
from transcription.transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError,
)

import logging
import os
import time

logger = logging.getLogger(__name__)
GENERIC_TRANSCRIPTION_ERROR = (
    "The uploaded audio could not be processed. Please try another file or contact support."
)


@shared_task
def add(x, y):
    time.sleep(5)
    return x + y


def process_audio(file_path: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")

    try:
        manager = TranscriptionManager(api_key, file_path)
        return manager.create_transcript()
    except TranscriptionMediaError:
        raise
    except Exception as exc:
        logger.exception("Unexpected transcription failure for file %s", file_path)
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
        transcript_text = process_audio(upload_path)

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
