from django.db import models

# Create your models here.
class Transcript(models.Model):
    name = models.CharField(max_length=255)
    audio_file = models.FileField(
        upload_to='uploads/audio/',
        default='uploads/audio/placeholder.mp3'
    )
    transcript_file = models.FileField(
        upload_to='uploads/transcripts/', 
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)