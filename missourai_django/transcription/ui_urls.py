from django.urls import path
from . import views

app_name = 'transcription'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_audio, name='upload_audio'),
    path('transcripts/', views.transcripts, name='transcripts'),
    path('transcripts/<int:transcript_id>/', views.view_transcript, name='view_transcript'),
    path('topics/', views.view_topics, name='view_topics'),
    path('add/', views.add_task_submit, name='add_task_submit'),
    path('add/<int:job_id>/', views.add_task_result, name='add_task_result'),
    path('celery/tasks/<uuid:task_id>/status/', views.celery_task_status, name='celery_task_status'),
]
