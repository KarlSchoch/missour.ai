from django import forms
from .models import Transcript

class TranscriptForm(forms.Form):
    name = forms.CharField(max_length=255)
    audio_file = forms.FileField()


class AddNumbersForm(forms.Form):
    x = forms.IntegerField(label="X")
    y = forms.IntegerField(label="Y")
