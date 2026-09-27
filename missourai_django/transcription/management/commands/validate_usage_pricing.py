from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from transcription.services.pricing_administration import validate_configuration


class Command(BaseCommand):
    help = "Validate all pricing periods and readiness of configured task models."

    def add_arguments(self, parser):
        parser.add_argument("--at", help="Optional ISO-8601 timestamp with timezone for a scheduled deployment.")

    def handle(self, *args, **options):
        at = None
        if options["at"]:
            try:
                at = parse_datetime(options["at"])
            except ValueError as exc:
                raise CommandError("--at must be an ISO-8601 timestamp with timezone.") from exc
            if at is None or timezone.is_naive(at):
                raise CommandError("--at must be an ISO-8601 timestamp with timezone.")
        states, errors = validate_configuration(at)
        for row in states:
            self.stdout.write(f"{row['task_type']} | {row['model_name']} | {'Pricing active' if row['ready'] else 'NOT READY'}")
        if errors:
            raise CommandError("Pricing validation failed:\n" + "\n".join(errors))
        self.stdout.write(self.style.SUCCESS("Usage pricing is valid."))
