from django.shortcuts import render, redirect
from django.http import HttpResponse
from .forms import AudioFileForm
from .models import AudioFile
import os

# Create handlers here
def handle_uploaded_file(f, name):
    # Define path where file will be saved and create directory if it doesn't exist
    directory = 'audio_files'
    if not os.path.exists(directory):
        os.makedirs(directory)

    path = os.path.join(directory, name)
    print(f"path writing to: {path}") # within root directory of the container
    # Need to do some validation to ensure
    ## File is an audio file
    ## name doesn't already exist in the directory

    # Write file to path
    with open(path, 'wb+') as destination:
        i = 1
        for chunk in f.chunks():
            print(f"writing chunk {i}")
            destination.write(chunk)
            i += 1

    # Perform additional logic here (i.e. transcription)
    ## Target: Transcribe each chunk into a single text file and create a new text file you save to and return from
    ## For now, ...

    # Return path to enable creating db record
    #return path

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
            # Print statements to check
            print(request.FILES['file'])
            print("run handle_uploaded_file function")
            handle_uploaded_file(request.FILES['file'], audio_file.name)
            #return redirect('success')
            return redirect('transcription:upload_audio')
    else:
        form = AudioFileForm()
    return render(request, 'transcription/upload.html', {'form': form})