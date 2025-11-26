from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .forms import TranscriptForm
from .models import Transcript, Topic
from .transcription_utils.transcription_manager import TranscriptionManager
from .tagging.tagging_manager import TaggingManager

import os
import logging
import json
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
            # Extract Selected Topics
            topics_raw = request.POST.get('topics', '[]')
            try:
                selected_topics = json.loads(topics_raw)
            except json.JSONDecodeError:
                selected_topics = []

            # Save audio file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                for chunk in audio_file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name

            # Check for the model_env
            # if os.getenv("MODEL_ENV") == "dev":
            #     print("MODEL_ENV is DEV.  Bypassing external API calls")
            #     print("selected_topics", selected_topics)
            #     return redirect('transcription:transcripts')
            # elif os.getenv("MODEL_ENV") in ["test", "prod"]:
            #     print("MODEL_ENV is TEST/PROD.  Making external API calls")
            #     return redirect('transcription:transcripts')
            # else:
            #     print("Enter valid value for MODEL_ENV: DEV, TEST, or PROD.")
            #     print(f"Current value: {os.getenv('MODEL_ENV')}")
            #     return redirect('transcription:transcripts')

            
            # Generate transcript
            transcript_text = process_audio(tmp_file_path)
            print("transcript_text", transcript_text)

            # Save the transcript text
            transcript_obj = Transcript(
                name=name,
                transcript_text=transcript_text,
            )
            transcript_obj.save()

            # Remove the temporary file
            os.remove(tmp_file_path)
            
            # Translate selected_topics into Topic objects
            selected_topics = [
                Topic(topic = x) for x in selected_topics
            ]

            # Tag the transcript based on selected topics
            tagging_manager = TaggingManager(
                api_key = os.getenv('OPENAI_API_KEY'),
                transcript=transcript_obj,
                topics = selected_topics
            )
            chunks = tagging_manager.chunk()
            print("Chunks created by tagging_manager.chunk()")
            print(chunks)
            tags = tagging_manager.tag_chunk(chunks[0])
            print("Tags created by tagging_manager.tag_chunk()")
            print(tags)


            # Redirect to transcripts page
            return redirect('transcription:transcripts')
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    return render(request, 'transcription/view_transcript.html', {'transcript': transcript})

@login_required
def dashboard(request):
    payload = {
        "username": "Karl", # request.user.get_username(),
        "apiUrls": {
            "ping": "/api/ping/",
            "items": "/api/items/",
        }
    }

    return render(request, "transcription/dashboard.html", {"initial_payload": payload})

@login_required
def analyze_audio_page_section(request):

    return render(
        request,
        "transcription/partials/analyze-audio-page-section.html",
    )