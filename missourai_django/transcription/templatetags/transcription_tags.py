from django import template
from ..models import Topic, Tag, Chunk
from collections import OrderedDict

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
    tags = list(
        Tag.objects
            .filter(chunk__transcript__pk = transcript.pk)
            .select_related('topic', 'chunk')
            .values(
                'chunk_id',
                'topic_id',
                'topic_present',
                'relevant_section',
                'topic__topic',
                'chunk__chunk_text'
            )
    )

    # Create structure for frontend
    ## Create topics
    topics = {}
    for tag in tags:
        tid = tag['topic_id']
        if tid not in topics:
            topics[tid] = {
                'id': tag['topic_id'],
                'name': tag['topic__topic']
            }
    topics = list(topics.values())
    ## Create rows
    ### Need a definitive list of chunks
    chunks = {}
    for tag in tags:
        cid = tag['chunk_id']
        if cid not in chunks:
            chunks[cid] = {
                'chunk_id': tag['chunk_id'],
                'text': tag['chunk__chunk_text'],
            }
    # Go through the chunks and select the tags related to that chunk
    print("* Validating chunks")
    for chunk in chunks:
        print("chunk", chunk)
        chunk_tags = [x for x in tags if x['chunk_id'] == chunk]
    # Based on the logic 

    ### Based on those chunks, pull out the cell values using topic id
    print("topics_map", topics)

    return { 'initial_payload': {'key': 'value'}} # list(tags) }

# [
#     {
#         'topic_present': False,
#         'relevant_section': '',
#         'topic__topic': 'Workforce Training',
#         'chunk__chunk_text': "Transportation, Infrastructure, and Public Safety will come to order, except that we'll go into subcommittee to start because we don't have a quorum yet. So Representative, if you want to hop up here, we'll do your bill. We'll start the testimony on your bill, and then once we get a quorum, we're going to go right into a vote on the roll call for a quorum so we can officially do a committee. So don't mind if we interrupt you in the middle of your testimony. So Representative Busick, go ahead on"
#     }, 
# ]