from django.db import models
from django.db.models import Q

# Create your models here.
class Transcript(models.Model):
    name = models.CharField(max_length=255)
    transcript_text = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

class Topic(models.Model):
    topic = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default='', blank=True)

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
    
    summary_type = models.CharField(
        max_length=20,
        choices=SummaryType.choices,
        default=SummaryType.GENERAL
    )
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="summaries"
    )
    text = models.TextField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="summary_topic_required_for_topic_type",
                check=(
                    Q(summary_type=SummaryType.GENERAL, topic__isnull=True) | Q(summary_type=SummaryType.TOPIC, topic__isnull=False)
                )
            )
        ]