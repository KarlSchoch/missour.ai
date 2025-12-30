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
            selected_topics_ct = len(selected_topics)
            selected_topics = list(
                Topic.objects.filter(topic__in=selected_topics)
            )
            assert len(selected_topics) == selected_topics_ct
            assert isinstance(selected_topics, list)
            for topic in selected_topics:
                assert isinstance(topic, Topic)

            # Tag the transcript based on selected topics
            tagging_manager = TaggingManager(
                api_key = os.getenv('OPENAI_API_KEY'),
                transcript=transcript_obj,
                topics = selected_topics
            )
            tags = tagging_manager.tag_transcript()

            # Redirect to transcripts page
            return redirect('transcription:transcripts')
    else:
        form = TranscriptForm()

    return render(request, 'transcription/upload_audio.html', {'form': form})

@login_required
def view_transcript(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id)
    if request.method == 'POST':
        # 1. Pull the tags out of the frontned
        topics_raw = request.POST.get('topics', '[]')
        try:
            topics_processed = json.loads(topics_raw)
        except json.JSONDecodeError:
            topics_processed = []
        # 2. TO DO: Conduct Data Validation
        # validate that you aren't getting an empty list of topics
        # if len(topics_processed) == 0:
        #     print("Please select valid topics")
        # Validate that you aren't getting duplicate topics
        # validate all your topics match 1:1 with topics in the DB

        # 3. Translate topics_processed into list[Topic]
        selected_topics = [
            x for x in Topic.objects.filter(topic__in=topics_processed)
        ]

        # 4. Tag the transcript based on selected topics
        tagging_manager = TaggingManager(
            api_key = os.getenv('OPENAI_API_KEY'),
            transcript = transcript,
            topics = selected_topics
        )
        tags = tagging_manager.tag_transcript()

        return render(
            request,
            'transcription/view_transcript.html',
            {'transcript': transcript}
        )

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