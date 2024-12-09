from django import forms
from .models import Transcript

class TranscriptForm(forms.ModelForm):
    class Meta:
        model = Transcript
        fields = ['name', 'audio_file']