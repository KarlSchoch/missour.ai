"""Recover delivery-gated billing without making any provider requests."""
from django.core.management.base import BaseCommand, CommandError

from transcription.models import TranscriptionBillingAttempt
from transcription.services.transcription_billing import (
    mark_transcription_not_billable, try_finalize_transcription_billing,
)


class Command(BaseCommand):
    help = "Finalize delivered transcription attempts, or explicitly close an abandoned attempt."

    def add_arguments(self, parser):
        parser.add_argument("--attempt-id", type=int)
        parser.add_argument("--abandon", action="store_true", help="Use only after confirming the worker stopped; fences late delivery.")
        parser.add_argument("--reason", default="")

    def handle(self, *args, **options):
        attempts = TranscriptionBillingAttempt.objects.all()
        if options["attempt_id"] is not None:
            attempts = attempts.filter(pk=options["attempt_id"])
            if not attempts.exists():
                raise CommandError("Attempt not found.")
        if options["abandon"]:
            if options["attempt_id"] is None or not options["reason"].strip():
                raise CommandError("Abandon requires --attempt-id and --reason after verifying worker termination.")
            attempt = attempts.get()
            if attempt.processing_state == "delivered":
                raise CommandError("Delivered attempts cannot be abandoned; reconcile their billing instead.")
            mark_transcription_not_billable(attempt.pk, options["reason"])
            self.stdout.write(f"Attempt {attempt.pk}: not billable.")
            return
        attempts = attempts.filter(processing_state="delivered").exclude(billing_state="finalized")
        unresolved = []
        for attempt_id in attempts.values_list("pk", flat=True):
            if try_finalize_transcription_billing(attempt_id):
                self.stdout.write(f"Attempt {attempt_id}: finalized.")
            else:
                unresolved.append(attempt_id)
        if unresolved:
            raise CommandError(f"Attempts still require usage evidence/reconciliation: {unresolved}")
