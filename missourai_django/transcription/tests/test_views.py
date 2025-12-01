from django.test import TestCase
from transcription.models import Transcript, Tag, Topic, Chunk

class ViewTranscriptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.transcript_one = Transcript.objects.create(
            name = "Dummy Transcript One",
            transcript_text = "Here is some dummy text about IT that should show up"
        )
        cls.transcript_two = Transcript.objects.create(
            name = "Dummy Transcript Two",
            transcript_text = "Here is some dummy text about IT that should NOT show up"
        )
        cls.topic_it = Topic.objects.create(
            topic = "Information Technology",
            description = ""
        )
        cls.topic_wf = Topic.objects.create(
            topic = "Workforce Training",
            description = ""
        )
        # Transcript One Related Elements
        cls.chunk_transcript_one = Chunk.objects.create(
            transcript = cls.transcript_one,
            chunk_text = cls.transcript_one.transcript_text
        )
        cls.tag_topic_it_transcript_one = Tag.objects.create(
            topic = cls.topic_it,
            chunk = cls.chunk_transcript_one,
            topic_present = True,
            relevant_section = "text about IT"
        )
        cls.tag_topic_wf_transcript_one = Tag.objects.create(
            topic = cls.topic_wf,
            chunk = cls.chunk_transcript_one,
            topic_present = False
        )
        # Transcript Two Related Elements
        cls.chunk_transcript_two = Chunk.objects.create(
            transcript = cls.transcript_two,
            chunk_text = cls.transcript_two.transcript_text
        )
        cls.tag_topic_it_transcript_two = Tag.objects.create(
            topic = cls.topic_it,
            chunk = cls.chunk_transcript_two,
            topic_present = True,
            relevant_section = "text about IT"
        )
        cls.tag_topic_wf_transcript_two = Tag.objects.create(
            topic = cls.topic_wf,
            chunk = cls.chunk_transcript_two,
            topic_present = False
        )


        
    def testViewTranscript(self):
        # assert that only Dummy Transcript One shows up
        assert False
    
    def testViewChunks(self):
        # Assert that you only return tags for a single transcript
        assert False