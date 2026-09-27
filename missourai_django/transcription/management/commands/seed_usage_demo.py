"""Create local dashboard fixtures without calling a model provider."""
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from transcription.models import ModelPrice, TaskPricing, UsageEvent
from transcription.services.pricing import (
    create_pending_usage_event, complete_duration_event, complete_token_event,
    mark_failed, mark_reconciliation_required, create_simulated_usage_event,
)


class Command(BaseCommand):
    help = 'Seed three months of labeled demo usage in the local SQLite database.'

    @transaction.atomic
    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if db['ENGINE'] != 'django.db.backends.sqlite3' or Path(db['NAME']).resolve() != (settings.BASE_DIR / 'db.sqlite3').resolve():
            raise CommandError('Demo seeding is limited to the local db.sqlite3 database.')
        now = timezone.now().astimezone(dt_timezone.utc)
        credentials = []
        users = []
        for name in ('viewer', 'alice', 'bob', 'carol'):
            username = f'usage-demo-{name}'
            user, created = get_user_model().objects.get_or_create(
                username=username, defaults={'first_name': 'Usage demo'},
            )
            if user.first_name != 'Usage demo':
                raise CommandError(f'{username} already exists and is not a demo account.')
            if created:
                password = secrets.token_urlsafe(16)
                user.set_password(password)
                user.save()
                credentials.append((username, password))
            if name == 'viewer':
                user.user_permissions.add(Permission.objects.get(
                    content_type__app_label='transcription', codename='view_all_usage',
                ))
            users.append(user)

        created_count = 0
        months = []
        for offset in range(3):
            month_index = now.year * 12 + now.month - 1 - offset
            year, month0 = divmod(month_index, 12)
            start = datetime(year, month0 + 1, 1, tzinfo=dt_timezone.utc)
            next_year, next_month0 = divmod(month_index + 1, 12)
            end = datetime(next_year, next_month0 + 1, 1, tzinfo=dt_timezone.utc)
            middle = start + timedelta(days=14)
            months.append(start.strftime('%Y-%m'))
            for task in ('transcription', 'summary', 'tagging'):
                model_name = f'usage-demo-{task}'
                for period_index, (begin, finish) in enumerate(((start, middle), (middle, end))):
                    audio = task == 'transcription'
                    price, _ = ModelPrice.objects.get_or_create(
                        provider='openai', model_name=model_name, effective_from=begin,
                        defaults={
                            'billing_unit': 'audio_duration' if audio else 'text_tokens',
                            'effective_to': finish, 'currency': 'USD',
                            'rate_per_minute': Decimal('0.006') if audio else None,
                            'input_rate_per_million': None if audio else Decimal('1.25'),
                            'cached_input_rate_per_million': None if audio else Decimal('0.50'),
                            'output_rate_per_million': None if audio else Decimal('5'),
                        },
                    )
                    TaskPricing.objects.get_or_create(
                        task_type=task, model_price=price, effective_from=begin,
                        defaults={'effective_to': finish, 'multiplier': Decimal('2') + period_index},
                    )
                for user_index, user in enumerate(users):
                    for sequence in range(12):
                        key = f'usage-demo:v1:{user.pk}:{start:%Y-%m}:{task}:{sequence}'
                        if UsageEvent.objects.filter(idempotency_key=key).exists():
                            continue
                        # Spread events through elapsed time, never into the future.
                        occurred_at = start + (min(now, end) - start) * ((sequence + 0.5) / 12)
                        kwargs = dict(
                            user=user, task_type=task, provider='openai', model_name=model_name,
                            idempotency_key=key, occurred_at=occurred_at,
                            calculation_details={'demo': True, 'dataset': 'usage-demo:v1'},
                        )
                        if sequence == 11:
                            create_simulated_usage_event(**kwargs)
                        else:
                            event = create_pending_usage_event(**kwargs)
                            if sequence == 10:
                                mark_failed(event, reason='Demo provider failure')
                            elif sequence == 9:
                                mark_reconciliation_required(event, reason='Demo missing billing metadata')
                            elif sequence != 8:
                                scale = (user_index + 1) * (sequence + 1)
                                if task == 'transcription':
                                    complete_duration_event(event, audio_duration_seconds=Decimal(180 * scale))
                                else:
                                    complete_token_event(event, input_tokens=12000 * scale, cached_input_tokens=1000 * scale, output_tokens=3000 * scale)
                        created_count += 1
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} demo events. Months: {", ".join(months)}'))
        self.stdout.write('These are synthetic charges on demo accounts, not real provider calls.')
        for username, password in credentials:
            self.stdout.write(f'{username} password: {password}')
        if not credentials:
            self.stdout.write('Existing demo passwords were preserved; use changepassword if needed.')
