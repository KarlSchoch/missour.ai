from django.db import models

# Create your models here.
class Transcript(models.Model):
    name = models.CharField(max_length=255)
    transcript_text = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

class Topic(models.Model):
    topic = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default='', blank=True)

class Chunk(models.model):
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE)
    chunk_text = models.TextField(default='')
