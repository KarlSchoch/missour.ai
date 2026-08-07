from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.conf import settings
from django.db import models
from django.utils import timezone


def _overlapping_effective_periods(queryset, effective_from, effective_to):
    queryset = queryset.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=effective_from)
    )
    if effective_to is not None:
        queryset = queryset.filter(effective_from__lt=effective_to)
    return queryset


def _validate_referenced_pricing_change(instance, original):
    if not instance.usage_events.exists():
        return

    immutable_fields = [
        field.attname
        for field in instance._meta.concrete_fields
        if field.name not in {"effective_to", "created_at"}
    ]
    changed_fields = [
        field_name
        for field_name in immutable_fields
        if getattr(instance, field_name) != getattr(original, field_name)
    ]
    if changed_fields:
        raise ValidationError(
            "Pricing referenced by usage events cannot be changed. "
            "Create a new effective-dated pricing record instead."
        )

    if instance.effective_to == original.effective_to:
        return
    if original.effective_to is not None or instance.effective_to is None:
        raise ValidationError(
            {"effective_to": "A referenced pricing period can only be closed once."}
        )
    if instance.usage_events.filter(occurred_at__gte=instance.effective_to).exists():
        raise ValidationError(
            {
                "effective_to": (
                    "The pricing period cannot end before an existing usage event."
                )
            }
        )


class ModelPrice(models.Model):
    class Provider(models.TextChoices):
        OPENAI = "openai", "OpenAI"

    class BillingUnit(models.TextChoices):
        TEXT_TOKENS = "text_tokens", "Text tokens"
        AUDIO_DURATION = "audio_duration", "Audio duration"

    provider = models.CharField(
        max_length=50,
        choices=Provider.choices,
        default=Provider.OPENAI,
    )
    model_name = models.CharField(max_length=100)
    billing_unit = models.CharField(max_length=30, choices=BillingUnit.choices)
    input_rate_per_million = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    cached_input_rate_per_million = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    output_rate_per_million = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    rate_per_minute = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=3, default="USD")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_model_prices",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "provider", "model_name"]
        indexes = [
            models.Index(
                fields=[
                    "provider",
                    "model_name",
                    "billing_unit",
                    "currency",
                    "effective_from",
                ]
            ),
        ]
        constraints = [
            models.CheckConstraint(
                name="model_price_end_after_start",
                condition=(
                    Q(effective_to__isnull=True)
                    | Q(effective_to__gt=models.F("effective_from"))
                ),
            ),
            models.CheckConstraint(
                name="model_price_nonnegative_rates",
                condition=(
                    (Q(input_rate_per_million__isnull=True) | Q(input_rate_per_million__gte=0))
                    & (
                        Q(cached_input_rate_per_million__isnull=True)
                        | Q(cached_input_rate_per_million__gte=0)
                    )
                    & (Q(output_rate_per_million__isnull=True) | Q(output_rate_per_million__gte=0))
                    & (Q(rate_per_minute__isnull=True) | Q(rate_per_minute__gte=0))
                ),
            ),
            models.CheckConstraint(
                name="model_price_rates_match_unit",
                condition=(
                    Q(
                        billing_unit="text_tokens",
                        input_rate_per_million__isnull=False,
                        output_rate_per_million__isnull=False,
                        rate_per_minute__isnull=True,
                    )
                    | Q(
                        billing_unit="audio_duration",
                        input_rate_per_million__isnull=True,
                        cached_input_rate_per_million__isnull=True,
                        output_rate_per_million__isnull=True,
                        rate_per_minute__isnull=False,
                    )
                ),
            ),
        ]

    def clean(self):
        super().clean()
        self.provider = self.provider.strip().lower()
        self.model_name = self.model_name.strip()
        self.currency = self.currency.strip().upper()

        errors = {}
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            errors["effective_to"] = "Effective end must be later than effective start."

        rate_fields = {
            "input_rate_per_million": self.input_rate_per_million,
            "cached_input_rate_per_million": self.cached_input_rate_per_million,
            "output_rate_per_million": self.output_rate_per_million,
            "rate_per_minute": self.rate_per_minute,
        }
        for field_name, value in rate_fields.items():
            if value is not None and value < Decimal("0"):
                errors[field_name] = "Rates cannot be negative."

        if self.billing_unit == self.BillingUnit.TEXT_TOKENS:
            if self.input_rate_per_million is None:
                errors["input_rate_per_million"] = "Text-token pricing requires an input rate."
            if self.output_rate_per_million is None:
                errors["output_rate_per_million"] = "Text-token pricing requires an output rate."
            if self.rate_per_minute is not None:
                errors["rate_per_minute"] = "Text-token pricing cannot define a per-minute rate."
        elif self.billing_unit == self.BillingUnit.AUDIO_DURATION:
            if self.rate_per_minute is None:
                errors["rate_per_minute"] = "Audio-duration pricing requires a per-minute rate."
            for field_name in (
                "input_rate_per_million",
                "cached_input_rate_per_million",
                "output_rate_per_million",
            ):
                if getattr(self, field_name) is not None:
                    errors[field_name] = "Audio-duration pricing cannot define token rates."

        if not errors and self.effective_from is not None:
            overlapping = _overlapping_effective_periods(
                ModelPrice.objects.filter(
                    provider=self.provider,
                    model_name=self.model_name,
                    billing_unit=self.billing_unit,
                    currency=self.currency,
                ).exclude(pk=self.pk),
                self.effective_from,
                self.effective_to,
            )
            if overlapping.exists():
                errors["__all__"] = (
                    "Effective periods cannot overlap for the same provider, model, "
                    "billing unit, and currency."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            original = ModelPrice.objects.get(pk=self.pk)
            _validate_referenced_pricing_change(self, original)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.usage_events.exists():
            raise ValidationError(
                "Pricing referenced by usage events cannot be deleted."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.provider}:{self.model_name} ({self.billing_unit}, "
            f"{self.currency}, {self.effective_from:%Y-%m-%d})"
        )


class TaskPricing(models.Model):
    class TaskType(models.TextChoices):
        TRANSCRIPTION = "transcription", "Transcription"
        SUMMARY = "summary", "Summary"
        TAGGING = "tagging", "Tagging"

    task_type = models.CharField(max_length=30, choices=TaskType.choices)
    model_price = models.ForeignKey(
        ModelPrice,
        on_delete=models.PROTECT,
        related_name="task_pricings",
    )
    multiplier = models.DecimalField(max_digits=12, decimal_places=6)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_task_pricings",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "task_type"]
        indexes = [
            models.Index(fields=["task_type", "model_price", "effective_from"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="task_pricing_positive_multiplier",
                condition=Q(multiplier__gt=0),
            ),
            models.CheckConstraint(
                name="task_pricing_end_after_start",
                condition=(
                    Q(effective_to__isnull=True)
                    | Q(effective_to__gt=models.F("effective_from"))
                ),
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.multiplier is not None and self.multiplier <= Decimal("0"):
            errors["multiplier"] = "Multiplier must be greater than zero."
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            errors["effective_to"] = "Effective end must be later than effective start."

        model_price = self.model_price if self.model_price_id else None
        if model_price is not None and self.effective_from is not None:
            if self.effective_from < model_price.effective_from:
                errors["effective_from"] = (
                    "Task pricing cannot begin before its model price."
                )
            if model_price.effective_to is not None:
                if self.effective_to is None or self.effective_to > model_price.effective_to:
                    errors["effective_to"] = (
                        "Task pricing must end no later than its model price."
                    )

        if not errors and self.effective_from is not None and self.model_price_id:
            overlapping = _overlapping_effective_periods(
                TaskPricing.objects.filter(
                    task_type=self.task_type,
                    model_price_id=self.model_price_id,
                ).exclude(pk=self.pk),
                self.effective_from,
                self.effective_to,
            )
            if overlapping.exists():
                errors["__all__"] = (
                    "Effective periods cannot overlap for the same task and model price."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            original = TaskPricing.objects.get(pk=self.pk)
            _validate_referenced_pricing_change(self, original)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.usage_events.exists():
            raise ValidationError(
                "Pricing referenced by usage events cannot be deleted."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.get_task_type_display()} using {self.model_price.model_name} "
            f"at {self.multiplier}x"
        )

# Create your models here.
class BackgroundJob(models.Model):
    class Kind(models.TextChoices):
        TRANSCRIPTION = "transcription", "Transcription"
        TAGGING = "tagging", "Tagging"
        SUMMARY = "summary", "Summary"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="background_jobs"
    )
    task_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=50, choices=Kind.choices)
    label = models.CharField(max_length=255)
    related_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.label} ({self.kind})"


class Transcript(models.Model):
    name = models.CharField(max_length=255)
    transcript_text = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transcripts"
    )


class TranscriptionJobMetric(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    background_job = models.OneToOneField(
        BackgroundJob,
        on_delete=models.CASCADE,
        related_name="transcription_metric",
    )
    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.CASCADE,
        related_name="transcription_metrics",
    )
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    audio_duration_sec = models.FloatField(null=True, blank=True)
    normalized_duration_sec = models.FloatField(null=True, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    max_concurrent_chunks = models.PositiveIntegerField(default=1)
    model_name = models.CharField(max_length=100, blank=True, default="")
    worker_hostname = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total_duration_sec = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    error_type = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Transcription metrics for job {self.background_job_id} ({self.status})"


class TranscriptionChunkMetric(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    job_metric = models.ForeignKey(
        TranscriptionJobMetric,
        on_delete=models.CASCADE,
        related_name="chunk_metrics",
    )
    chunk_index = models.PositiveIntegerField()
    start_time_sec = models.FloatField()
    duration_sec = models.FloatField()
    split_depth = models.PositiveIntegerField(default=0)
    chunk_file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    ffmpeg_duration_sec = models.FloatField(null=True, blank=True)
    openai_duration_sec = models.FloatField(null=True, blank=True)
    total_duration_sec = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    error_type = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["job_metric", "chunk_index"]),
            models.Index(fields=["started_at", "finished_at"]),
        ]

    def __str__(self):
        return (
            f"Chunk {self.chunk_index} for transcription metric "
            f"{self.job_metric_id} ({self.status})"
        )

class Topic(models.Model):
    topic = models.CharField(
        max_length=100,
        unique=True
    )
    description = models.CharField(max_length=255, default='', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topics"
    )

    def __str__(self):
        return f"Topic: {self.topic}; Description: {self.description[:50]}"

class Chunk(models.Model):
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE)
    chunk_text = models.TextField(default='')
    topics = models.ManyToManyField(Topic, through="Tag", related_name="chunks")
    def __str__(self):
        return f"Transcript: {self.transcript}; Chunk Text: {self.chunk_text}; Topics: {self.topics}"

class Tag(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="tags"
    )
    chunk = models.ForeignKey(
        Chunk,
        on_delete=models.CASCADE,
        related_name="tags"
    )
    topic_present = models.BooleanField(default=False)
    relevant_section = models.TextField(default='')
    user_validation = models.BooleanField(default=False)

    def __str__(self):
        return f"Topic: {self.topic}; Chunk: {self.chunk}; Topic Present: {self.topic_present}; Relevant Section: {self.relevant_section}; User Validation: {self.user_validation}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "topic"],
                name="uniq_chunk_topic",
            )
        ]

class Summary(models.Model):
    class SummaryType(models.TextChoices):
        GENERAL = "general", "General"
        TOPIC = "topic", "Topic"
    
    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.CASCADE,
        related_name="summaries"
    )
    summary_type = models.CharField(
        max_length=20,
        choices=SummaryType.choices,
        default=SummaryType.GENERAL
    )
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="summaries"
    )
    text = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="summary_topic_required_for_topic_type",
                condition=(
                    Q(summary_type="general", topic__isnull=True) | Q(summary_type="topic", topic__isnull=False)
                )
            )
        ]


class UsageEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Usage events must be updated through their validated lifecycle."
        )

    def delete(self):
        raise ValidationError("Usage events are immutable and cannot be deleted.")


class UsageEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        RECONCILIATION_REQUIRED = (
            "reconciliation_required",
            "Reconciliation required",
        )
        SIMULATED = "simulated", "Simulated"

    class UsageSource(models.TextChoices):
        PROVIDER = "provider", "Provider"
        DURATION = "duration", "Duration"
        SIMULATED = "simulated", "Simulated"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="usage_events",
    )
    task_type = models.CharField(
        max_length=30,
        choices=TaskPricing.TaskType.choices,
    )
    provider = models.CharField(
        max_length=50,
        choices=ModelPrice.Provider.choices,
        default=ModelPrice.Provider.OPENAI,
    )
    model_name = models.CharField(max_length=100)
    occurred_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    billing_unit = models.CharField(
        max_length=30,
        choices=ModelPrice.BillingUnit.choices,
    )
    usage_source = models.CharField(max_length=20, choices=UsageSource.choices)

    input_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    cached_input_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    output_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    audio_duration_seconds = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
    )

    model_price = models.ForeignKey(
        ModelPrice,
        on_delete=models.PROTECT,
        related_name="usage_events",
    )
    task_pricing = models.ForeignKey(
        TaskPricing,
        on_delete=models.PROTECT,
        related_name="usage_events",
    )
    base_cost = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    multiplier = models.DecimalField(max_digits=12, decimal_places=6)
    billed_cost = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=3, default="USD")
    calculation_details = models.JSONField(default=dict, blank=True)

    provider_request_id = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, unique=True)

    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    summary = models.ForeignKey(
        Summary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    transcription_chunk = models.ForeignKey(
        TranscriptionChunkMetric,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UsageEventQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["user", "occurred_at"]),
            models.Index(fields=["task_type", "occurred_at"]),
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["transcript", "occurred_at"]),
            models.Index(fields=["summary", "occurred_at"]),
            models.Index(fields=["tag", "occurred_at"]),
            models.Index(fields=["transcription_chunk", "occurred_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="usage_event_nonnegative_values",
                condition=(
                    (
                        Q(audio_duration_seconds__isnull=True)
                        | Q(audio_duration_seconds__gte=0)
                    )
                    & (Q(base_cost__isnull=True) | Q(base_cost__gte=0))
                    & (Q(billed_cost__isnull=True) | Q(billed_cost__gte=0))
                    & Q(multiplier__gt=0)
                ),
            ),
            models.CheckConstraint(
                name="usage_event_quantity_matches_unit",
                condition=(
                    Q(
                        billing_unit="text_tokens",
                        audio_duration_seconds__isnull=True,
                    )
                    | Q(
                        billing_unit="audio_duration",
                        input_tokens__isnull=True,
                        cached_input_tokens__isnull=True,
                        output_tokens__isnull=True,
                    )
                ),
            ),
            models.CheckConstraint(
                name="usage_event_succeeded_has_costs",
                condition=(
                    ~Q(status="succeeded")
                    | Q(base_cost__isnull=False, billed_cost__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="usage_event_simulated_is_zero",
                condition=(
                    ~Q(status="simulated")
                    | Q(
                        usage_source="simulated",
                        base_cost=0,
                        billed_cost=0,
                    )
                ),
            ),
        ]

    @property
    def is_billable(self):
        return self.status == self.Status.SUCCEEDED

    def clean(self):
        super().clean()
        self.provider = self.provider.strip().lower()
        self.model_name = self.model_name.strip()
        self.currency = self.currency.strip().upper()

        errors = {}
        for field_name in (
            "audio_duration_seconds",
            "base_cost",
            "billed_cost",
        ):
            value = getattr(self, field_name)
            if value is not None and value < Decimal("0"):
                errors[field_name] = "Value cannot be negative."
        if self.multiplier is not None and self.multiplier <= Decimal("0"):
            errors["multiplier"] = "Multiplier must be greater than zero."

        if self.billing_unit == ModelPrice.BillingUnit.TEXT_TOKENS:
            if self.audio_duration_seconds is not None:
                errors["audio_duration_seconds"] = (
                    "Text-token usage cannot include audio duration."
                )
        elif self.billing_unit == ModelPrice.BillingUnit.AUDIO_DURATION:
            for field_name in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
            ):
                if getattr(self, field_name) is not None:
                    errors[field_name] = (
                        "Audio-duration usage cannot include token quantities."
                    )

        if self.status == self.Status.SUCCEEDED:
            if self.base_cost is None:
                errors["base_cost"] = "Succeeded usage requires a base cost."
            if self.billed_cost is None:
                errors["billed_cost"] = "Succeeded usage requires a billed cost."
            if (
                self.billing_unit == ModelPrice.BillingUnit.TEXT_TOKENS
                and (self.input_tokens is None or self.output_tokens is None)
            ):
                errors["status"] = (
                    "Succeeded text-token usage requires input and output counts."
                )
            if (
                self.billing_unit == ModelPrice.BillingUnit.AUDIO_DURATION
                and self.audio_duration_seconds is None
            ):
                errors["status"] = (
                    "Succeeded audio-duration usage requires an audio duration."
                )

        if self.status == self.Status.SIMULATED:
            if self.usage_source != self.UsageSource.SIMULATED:
                errors["usage_source"] = "Simulated usage requires a simulated source."
            if self.base_cost != Decimal("0") or self.billed_cost != Decimal("0"):
                errors["status"] = "Simulated usage must have zero costs."
        elif self.usage_source == self.UsageSource.SIMULATED:
            errors["usage_source"] = "A simulated source requires simulated status."

        model_price = self.model_price if self.model_price_id else None
        task_pricing = self.task_pricing if self.task_pricing_id else None
        if model_price is not None:
            if self.provider != model_price.provider:
                errors["provider"] = "Provider must match the selected model price."
            if self.model_name != model_price.model_name:
                errors["model_name"] = "Model must match the selected model price."
            if self.billing_unit != model_price.billing_unit:
                errors["billing_unit"] = (
                    "Billing unit must match the selected model price."
                )
            if self.currency != model_price.currency:
                errors["currency"] = "Currency must match the selected model price."
            if self.occurred_at is not None and (
                self.occurred_at < model_price.effective_from
                or (
                    model_price.effective_to is not None
                    and self.occurred_at >= model_price.effective_to
                )
            ):
                errors["model_price"] = (
                    "Model price was not effective when the usage occurred."
                )

        if task_pricing is not None:
            if task_pricing.model_price_id != self.model_price_id:
                errors["task_pricing"] = (
                    "Task pricing must reference the selected model price."
                )
            if task_pricing.task_type != self.task_type:
                errors["task_type"] = "Task must match the selected task pricing."
            if self.multiplier != task_pricing.multiplier:
                errors["multiplier"] = (
                    "Multiplier must match the selected task pricing."
                )
            if self.occurred_at is not None and (
                self.occurred_at < task_pricing.effective_from
                or (
                    task_pricing.effective_to is not None
                    and self.occurred_at >= task_pricing.effective_to
                )
            ):
                errors["task_pricing"] = (
                    "Task pricing was not effective when the usage occurred."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            original = UsageEvent.objects.get(pk=self.pk)
            if original.status in {
                self.Status.SUCCEEDED,
                self.Status.FAILED,
                self.Status.SIMULATED,
            }:
                raise ValidationError(
                    "Completed usage events are immutable and cannot be changed."
                )
            immutable_fields = (
                "user_id",
                "task_type",
                "provider",
                "model_name",
                "occurred_at",
                "billing_unit",
                "usage_source",
                "model_price_id",
                "task_pricing_id",
                "multiplier",
                "currency",
                "idempotency_key",
            )
            if any(
                getattr(self, field_name) != getattr(original, field_name)
                for field_name in immutable_fields
            ):
                raise ValidationError(
                    "Usage identity and pricing snapshots cannot be changed."
                )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Usage events are immutable and cannot be deleted.")

    def __str__(self):
        return (
            f"{self.get_task_type_display()} usage for user {self.user_id} "
            f"at {self.occurred_at:%Y-%m-%d %H:%M:%S}"
        )
