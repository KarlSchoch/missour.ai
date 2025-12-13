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
    tags = Tag.objects.filter(chunk__transcript__pk = transcript.pk).select_related('topic', 'chunk').values('topic_present', 'relevant_section', 'topic__topic', 'chunk__chunk_text')

    return { 'initial_payload': list(tags.values()) }

[
    {
        'topic_present': False,
        'relevant_section': '',
        'topic__topic': 'Workforce Training',
        'chunk__chunk_text': "Transportation, Infrastructure, and Public Safety will come to order, except that we'll go into subcommittee to start because we don't have a quorum yet. So Representative, if you want to hop up here, we'll do your bill. We'll start the testimony on your bill, and then once we get a quorum, we're going to go right into a vote on the roll call for a quorum so we can officially do a committee. So don't mind if we interrupt you in the middle of your testimony. So Representative Busick, go ahead on"
    }, 
]