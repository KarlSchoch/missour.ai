from django import forms
from .models import Transcript

class TranscriptForm(forms.Form):
    name = forms.CharField(max_length=255)
    audio_file = forms.FileField()