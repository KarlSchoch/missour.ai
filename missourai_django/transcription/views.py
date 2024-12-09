from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from .forms import TranscriptForm
from .models import Transcript
import os

def process_audio(file_path):
    # Placeholder for transcript generation logic
    # Replace with transcription model
    return "Generated transcript text for the file."

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

def transcripts(request):
    transcripts = Transcript.objects.all()

    return render(
        request,
        'transcription/transcripts.html',
        {'transcripts': transcripts}
    )

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
            transcript_text = process_audio(audio_file.temporary_file_path())

            # Save the transcript as a file
            transcript_filename = f"{transcript_obj.name}_transcript.txt"
            transcript_obj.transcript_file.save(transcript_filename, ContentFile(transcript_text))

            # Save the object
            transcript_obj.save()

            # Redirect to transcripts page
            return redirect('transcription:transcripts')
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})