from django.shortcuts import render, redirect
from django.http import HttpResponse
from .forms import AudioFileForm

# Create your views here.
def index(request):
    return render(request, 'transcription/index.html')

def transcripts(request):
    return render(request, 'transcription/transcripts.html')

def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            #return redirect('success')
            return redirect('transcription:upload_audio')
    else:
        form = AudioFileForm()
    return render(request, 'transcription/upload.html', {'form': form})