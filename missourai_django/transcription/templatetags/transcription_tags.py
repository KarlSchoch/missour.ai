from django import template
from ..models import Topic, Tag, Chunk

register = template.Library()

@register.inclusion_tag(
    'transcription/partials/analyze-audio-page-section.html',
    takes_context=True,
)
def render_analyze_audio_section(context):
    topics = Topic.objects.all()

    payload = {
        'topics': [
            {'value': t.topic, 'label': t.topic}
            for t in topics
        ],
    }

    return {'initial_payload': payload}

@register.inclusion_tag(
    'transcription/partials/view-transcript-chunks-page-section.html',
    takes_context=True
)
def render_view_transcript_chunks_section(context):
    # Pull the transcript out of the context
    transcript = context.get('transcript')
    # Use that transcript to filer for tags related to that transcript
    tags = Tag.objects.filter(chunk__transcript__pk = transcript.pk)

    return { 'initial_payload': list(tags.values()) }