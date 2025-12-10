from django import template
from ..models import Topic, Tag

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
    # Planned structure for initial_payload contents
    # { 'initial_payload': [Tag] }
    print("transcript", context.get('transcript'))
    tags = Tag.objects.all()

    return { 'initial_payload': { 'key': 'value' } }