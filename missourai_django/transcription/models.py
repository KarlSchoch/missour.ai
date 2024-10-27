from django.db import models

# Create your models here.
class AudioFile(models.Model):
    name = models.CharField(max_length=100)
    file = models.FileField(upload_to='audio-files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)