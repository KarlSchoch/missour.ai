from django.db import models

# Create your models here.
class Transcript(models.Model):
    name = models.CharField(max_length=255)
    audio_file = models.FileField(upload_to='uploads/audio/')
    transcript_file = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)