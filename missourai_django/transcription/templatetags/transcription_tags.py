from django import template
from ..models import Topic, Tag, Chunk
from collections import OrderedDict
from django.urls import reverse

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
    # Pull the transcript out of the context and use for filtering
    transcript = context.get('transcript')
    

    # 1) pull the chunks (for row order + text)
    chunks = list(
        Chunk.objects
        .filter(transcript_id=transcript.pk)
        .values("id", "chunk_text")
        .order_by("id")  # or your real ordering field
    )

    # 2) pull the tags with topic metadata
    tag_rows = list(
        Tag.objects
        .filter(chunk__transcript_id=transcript.pk)
        .select_related("topic")
        .values(
            "chunk_id",
            "topic_id",
            "topic__topic",
            "topic_present",
            "relevant_section",
        )
    )

    # 3) build topic list (unique + stable)
    topic_map = OrderedDict()
    for tr in tag_rows:
        tid = tr["topic_id"]
        if tid not in topic_map:
            topic_map[tid] = {"id": tid, "name": tr["topic__topic"]}

    topics = list(topic_map.values())

    # 4) init row structure with empty cells for all topics
    rows_by_chunk = {
        c["id"]: {
            "chunk_id": c["id"],
            "text": c["chunk_text"],
            "cells": {t["id"]: "" for t in topics},
        }
        for c in chunks
    }

    # 5) fill cells based on tag_rows
    for tr in tag_rows:
        # val = tr["relevant_section"] if tr["topic_present"] else ""
        val = "Topic Present" if tr["topic_present"] else ""
        rows_by_chunk[tr["chunk_id"]]["cells"][tr["topic_id"]] = val

    payload = {"topics": topics, "rows": list(rows_by_chunk.values())}

    return { 'initial_payload': payload}

@register.inclusion_tag(
    'transcription/partials/generate-report-page-section.html',
    takes_context=True,
)
def render_generate_report_page_section(context):
    # Pull the transcript out of the context and use for filtering
    transcript = context.get('transcript')

    return {
        'initial_payload': {
            "transcript_id": transcript.pk,
            "apiUrls": {
                "topics": reverse("api:topic-list"),
                "summaries": reverse("api:summary-list")
            }
        }
    }