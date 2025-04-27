from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .forms import TranscriptForm
from .models import Transcript
from .transcription_utils.transcription_manager import TranscriptionManager
import os
import logging
import tempfile

def process_audio(file_path:str) -> str:
    # Intialize TranscriptionManager with OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")
    manager = TranscriptionManager(api_key, file_path)
    transcript_text = manager.create_transcript()
    
    return transcript_text

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

@login_required
def transcripts(request):
    transcripts = Transcript.objects.all()

    return render(
        request,
        'transcription/transcripts.html',
        {'transcripts': transcripts}
    )

@login_required
def upload_audio(request):
    if request.method == 'POST':
        form = TranscriptForm(request.POST, request.FILES)
        if form.is_valid():
            name = form.cleaned_data['name']
            audio_file = form.cleaned_data['audio_file']

            # Save audio file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                for chunk in audio_file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name

            # Generate transcript
            transcript_text = process_audio(tmp_file_path)

            # Save the transcript text
            transcript_obj = Transcript(
                name=name,
                transcript_text=transcript_text,
            )
            transcript_obj.save()

            # Remove the temporary file
            os.remove(tmp_file_path)

            # Redirect to transcripts page
            return redirect('transcription:transcripts')
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    return render(request, 'transcription/view_transcript.html', {'transcript': transcript})
