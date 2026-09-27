"""Delivery-gated transcription charges. Never perform provider calls here."""

import logging
from decimal import Decimal, localcontext

from django.db import transaction
from django.utils import timezone

from transcription.models import (
    Transcript, TranscriptionBillingAttempt, TranscriptionChunkMetric,
    TranscriptionJobMetric, UsageEvent,
)
from .pricing import UsageEventLifecycleError, _quantize_cost

logger = logging.getLogger(__name__)


@transaction.atomic
def claim_transcription_attempt(job, transcript):
    # Lock the job before creating/claiming its single attempt. A redelivery must
    # not restart paid work. A deliberate retry requires a new background job.
    type(job).objects.select_for_update().get(pk=job.pk)
    attempt, _ = TranscriptionBillingAttempt.objects.get_or_create(
        background_job=job, defaults={"transcript": transcript},
    )
    if attempt.transcript_id != transcript.pk:
        raise UsageEventLifecycleError("Attempt belongs to another transcript.")
    if attempt.claimed_at is not None or attempt.processing_state != "processing":
        return None
    attempt.claimed_at = timezone.now()
    attempt.save(update_fields=["claimed_at", "updated_at"])
    return attempt


@transaction.atomic
def record_transcript_delivery(attempt_id, transcript_text):
    attempt = TranscriptionBillingAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt.processing_state == "delivered":
        return
    if attempt.processing_state != "processing":
        raise UsageEventLifecycleError("Cannot deliver a closed transcription attempt.")
    # Empty text is valid for silent audio; delivery is an explicit state.
    transcript = Transcript.objects.select_for_update().get(pk=attempt.transcript_id)
    transcript.transcript_text = transcript_text
    transcript.save(update_fields=["transcript_text"])
    attempt.processing_state = "delivered"
    attempt.delivered_at = timezone.now()
    attempt.save(update_fields=["processing_state", "delivered_at", "updated_at"])


@transaction.atomic
def finalize_transcription_billing(attempt_id):
    attempt = TranscriptionBillingAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt.billing_state == "finalized":
        return
    if attempt.processing_state != "delivered":
        raise UsageEventLifecycleError("Billing requires a durably delivered transcript.")
    events = list(attempt.usage_events.select_for_update().order_by("pk"))
    if not events:
        raise UsageEventLifecycleError("Delivered attempt has no usage evidence.")
    for event in events:
        # Failed parent requests may have been recovered by splitting their
        # audio range. Successful assembly, not every request succeeding, is
        # the delivery boundary. Never charge failed or simulated requests.
        if event.status in {UsageEvent.Status.FAILED, UsageEvent.Status.SIMULATED}:
            continue
        if (
            event.status not in {UsageEvent.Status.AWAITING_DELIVERY, UsageEvent.Status.RECONCILIATION_REQUIRED}
            or event.base_cost is None
            or event.audio_duration_seconds is None
            or event.provider_outcome != UsageEvent.ProviderOutcome.SUCCEEDED
        ):
            raise UsageEventLifecycleError(f"Usage event {event.pk} needs reconciliation.")
        with localcontext() as context:
            context.prec = 50
            event.billed_cost = _quantize_cost(event.base_cost * event.multiplier)
        event.status = UsageEvent.Status.SUCCEEDED
        event.save()
    attempt.billing_state = "finalized"
    attempt.finalized_at = timezone.now()
    attempt.error_message = ""
    attempt.save(update_fields=["billing_state", "finalized_at", "error_message", "updated_at"])


def try_finalize_transcription_billing(attempt_id):
    """Billing errors must never undo delivery or provoke another provider call."""
    try:
        finalize_transcription_billing(attempt_id)
        return True
    except Exception as exc:
        logger.exception("transcription_billing_reconciliation_required attempt_id=%s", attempt_id)
        try:
            with transaction.atomic():
                attempt = TranscriptionBillingAttempt.objects.select_for_update().get(pk=attempt_id)
                if attempt.processing_state == "delivered" and attempt.billing_state != "finalized":
                    attempt.billing_state = "reconciliation_required"
                    attempt.error_message = str(exc)
                    attempt.save(update_fields=["billing_state", "error_message", "updated_at"])
                    for event in attempt.usage_events.select_for_update().filter(status=UsageEvent.Status.AWAITING_DELIVERY):
                        event.status = UsageEvent.Status.RECONCILIATION_REQUIRED
                        event.save()
        except Exception:
            # The durable delivered/pending record remains discoverable even
            # when the database cannot currently accept a reconciliation flag.
            logger.exception("transcription_billing_flag_failed attempt_id=%s", attempt_id)
        return False


@transaction.atomic
def mark_transcription_not_billable(attempt_id, reason):
    attempt = TranscriptionBillingAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt.processing_state == "delivered":
        return  # A subsequent tagging failure does not revoke delivery.
    attempt.processing_state = "failed"
    attempt.billing_state = "not_billable"
    attempt.error_message = str(reason)
    attempt.save(update_fields=["processing_state", "billing_state", "error_message", "updated_at"])
    TranscriptionJobMetric.objects.filter(background_job_id=attempt.background_job_id).update(
        status=TranscriptionJobMetric.Status.FAILED, finished_at=timezone.now(),
        error_message=str(reason),
    )
    TranscriptionChunkMetric.objects.filter(
        job_metric__background_job_id=attempt.background_job_id,
        status=TranscriptionChunkMetric.Status.RUNNING,
    ).update(status=TranscriptionChunkMetric.Status.FAILED, finished_at=timezone.now(), error_message=str(reason))
    for event in attempt.usage_events.select_for_update().order_by("pk"):
        if event.status in {UsageEvent.Status.FAILED, UsageEvent.Status.SIMULATED, UsageEvent.Status.NOT_BILLABLE}:
            continue
        event.status = UsageEvent.Status.NOT_BILLABLE
        event.billed_cost = Decimal("0")
        event.save()


def record_transcription_usage(usage_event, **kwargs):
    from .pricing import complete_duration_event

    if not usage_event.transcription_attempt_id:
        raise UsageEventLifecycleError("Transcription usage requires a billing attempt.")
    return complete_duration_event(usage_event, **kwargs)
