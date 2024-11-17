from django.shortcuts import render, redirect
from django.http import HttpResponse
from .forms import AudioFileForm
from .models import AudioFile
import os

# Create handlers here
def handle_uploaded_file(f, name):
    # Define path where file will be saved and create directory if it doesn't exist
    # Need to do some validation to ensure
    ## File is an audio file
    ## name doesn't already exist in the directory
    directory = 'audio_files'
    if not os.path.exists(directory):
        os.makedirs(directory)
    path = os.path.join(directory, name)
    print(f"path writing to: {path}") # within root directory of the container

    # Write file to path
    with open(path, 'wb+') as destination:
        file_content = f.read()
        destination.write(file_content)

    # Create transcript of audio file
    transcript_path = f"{path}_transcript.txt"
    with open(transcript_path, 'wb+') as destination:
        destination.write(b"trancsript of audio file")

    # Return path to transcript enable creating db record
    return transcript_path

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

def transcripts(request):
    return render(request, 'transcription/transcripts.html')

def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileForm(request.POST, request.FILES)
        if form.is_valid():
            # Save form instance but don't commit to db yet
            audio_file = form.save(commit=False)
            # Create transcript of audio file, returning path to transcript
            transcript_path = handle_uploaded_file(request.FILES['file'], audio_file.name)
            print(f"transcript_path: {transcript_path}")
            # Create transcript record in db
            #return redirect('success')
            #return redirect('transcription:upload_audio')
            return redirect('transcription:transcripts')
    else:
        form = AudioFileForm()
    return render(request, 'transcription/upload.html', {'form': form})