from django.shortcuts import render, redirect
from django.http import HttpResponse
from .forms import AudioFileForm
from .models import AudioFile, Transcript
import os

# Create handlers here
def handle_uploaded_file(f, name):
    # Define path where file will be saved and create directory if it doesn't exist
    # Need to do some validation to ensure
    ## File is an audio file
    ## name doesn't already exist in the directory
    audio_directory = 'audio_files'
    transcript_directory = 'transcripts'
    if not os.path.exists(audio_directory):
        os.makedirs(audio_directory)
    if not os.path.exists(transcript_directory):
        os.makedirs(transcript_directory)
    audio_path = os.path.join(audio_directory, name)
    transcript_path = os.path.join(transcript_directory, name)
    print(f"audio path writing to: {audio_path}") # within root directory of the container
    print(f"transcript path writing to: {transcript_path}") # within root directory of the container

    # Write audio file
    with open(audio_path, 'wb+') as destination:
        file_content = f.read()
        destination.write(file_content)

    # Create transcript of audio file and write to path
    with open(transcript_path, 'wb+') as destination:
        destination.write(b"transcript of audio file")

    # TO DO: Delete audio file from disk

    # Return path to transcript enable creating db record
    return transcript_path

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

def transcripts(request):
    transcripts = Transcript.objects.all()
    print("transcripts returned")
    i = 1
    for transcript in transcripts:
        print(f"transcript {i}")
        print(transcript.name)
        print(transcript.transcript_file)
        i += 1
        print("*")
    return render(
        request,
        'transcription/transcripts.html',
        {'transcripts': transcripts}
    )

def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileForm(request.POST, request.FILES)
        if form.is_valid():
            # Save form instance but don't commit to db yet
            audio_file = form.save(commit=False)
            # Create transcript of audio file, returning path to transcript
            transcript_path = handle_uploaded_file(request.FILES['file'], audio_file.name)
            print(f"transcript_path: {transcript_path}")
            # Create transcript record in db based on returned path
            transcript = Transcript.objects.create(
                name=audio_file.name,
                transcript_file=transcript_path
            )
            # Delete all audio file related records from machine and DB

            # direct user to transcripts page
            #return redirect('success')
            #return redirect('transcription:upload_audio')
            return redirect('transcription:transcripts')
    else:
        form = AudioFileForm()
    return render(request, 'transcription/upload.html', {'form': form})