from django import forms
from .models import Transcript

class TranscriptForm(forms.Form):
    name = forms.CharField(max_length=255)
    audio_file = forms.FileField()


class YouTubeForm(forms.Form):
    youtube_url = forms.URLField(label="YouTube video URL", max_length=2048)
    name = forms.CharField(label="Transcript name", max_length=255, required=False)
    authorized = forms.BooleanField(label="I am authorized to process this video's content.")
    retry = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def clean_youtube_url(self):
        from .transcription_utils.sources import SourceError, youtube_source
        try:
            self.video_id, canonical = youtube_source(self.cleaned_data["youtube_url"])
        except SourceError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return canonical
