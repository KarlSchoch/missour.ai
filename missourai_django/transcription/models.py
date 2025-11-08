from django.db import models

# Create your models here.
class Transcript(models.Model):
    name = models.CharField(max_length=255)
    transcript_text = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

class Topic(models.Model):
    topic = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default='', blank=True)

class Chunk(models.Model):
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE)
    chunk_text = models.TextField(default='')
    topics = models.ManyToManyField(Topic, through="Tag", related_name="chunks")

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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "topic"],
                name="uniq_chunk_topic",
            )
        ]