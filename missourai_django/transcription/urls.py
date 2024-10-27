from django.urls import path
from . import views

app_name = 'transcription'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_audio, name='upload_audio'),
]