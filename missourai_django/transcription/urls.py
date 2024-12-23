from django.urls import path
from . import views

app_name = 'transcription'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_audio, name='upload_audio'),
    path('transcripts/', views.transcripts, name='transcripts'),
    path('transcripts/<int:transcript_id>/', views.view_transcript, name='view_transcript'),
]