from django.db import models
from django.db.models import Q
from django.conf import settings

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
