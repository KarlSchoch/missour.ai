from django.contrib import admin

# Register your models here.
from .models import (
    BackgroundJob,
    Chunk,
    Summary,
    Tag,
    Topic,
    Transcript,
    TranscriptionChunkMetric,
    TranscriptionJobMetric,
)

admin.site.register([
    BackgroundJob,
    Transcript,
    Topic,
    Chunk,
    Tag,
    Summary,
    TranscriptionJobMetric,
    TranscriptionChunkMetric,
])
