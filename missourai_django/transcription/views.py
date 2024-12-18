from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from .forms import TranscriptForm
from .models import Transcript
from .transcription_utils.transcription_manager import TranscriptionManager
import os
import logging

def process_audio(file_path:str) -> str:
    # Intialize TranscriptionManager with OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set.")
    manager = TranscriptionManager(api_key)
    transcript_text = manager.create_transcript(file_path)
    
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
            transcript_obj = form.save(commit=False)
            audio_file = request.FILES['audio_file']

            # Save audio file
            transcript_obj.audio_file = audio_file
            transcript_obj.save()

            # Generate transcript
            audio_file_path = transcript_obj.audio_file.path
            print(f"Audio file path: {audio_file_path}")
            transcript_text = process_audio(audio_file_path)

            # Build path for transcript file based on model's default location
            transcript_filename = f"{transcript_obj.name}_transcript.txt"
            transcript_dir = os.path.dirname(transcript_obj.transcript_file.field.upload_to)
            transcript_path = os.path.join(transcript_dir, transcript_filename)

            # Ensure directory exists
            if not os.path.exists(transcript_dir):
                os.makedirs(transcript_dir)

            # Save the transcript as a file
            with open(transcript_path, 'w') as f:
                f.write(transcript_text)
            transcript_obj.transcript_file.save(transcript_filename, ContentFile(transcript_text))

            # Save the object
            transcript_obj.save()

            # Redirect to transcripts page
            return redirect('transcription:transcripts')
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})