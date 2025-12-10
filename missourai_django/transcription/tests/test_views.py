from django.test import TestCase
from transcription.models import Transcript, Tag, Topic, Chunk
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class ViewTranscriptTests(TestCase):
    def setUp(self):
        # Authentication
        self.user = User.objects.create_user(username='test', password='pw')
        self.client.force_login(self.user)
        # Base Records
        self.transcript_one = Transcript.objects.create(
            name = "Dummy Transcript One",
            transcript_text = "Here is some dummy text about IT that should show up"
        )
        self.transcript_two = Transcript.objects.create(
            name = "Dummy Transcript Two",
            transcript_text = "Here is some dummy text about IT that should NOT show up"
        )
        self.topic_it = Topic.objects.create(
            topic = "Information Technology",
            description = ""
        )
        self.topic_wf = Topic.objects.create(
            topic = "Workforce Training",
            description = ""
        )
        # Transcript One Related Elements
        self.chunk_transcript_one = Chunk.objects.create(
            transcript = self.transcript_one,
            chunk_text = self.transcript_one.transcript_text
        )
        self.tag_topic_it_transcript_one = Tag.objects.create(
            topic = self.topic_it,
            chunk = self.chunk_transcript_one,
            topic_present = True,
            relevant_section = "text about IT"
        )
        self.tag_topic_wf_transcript_one = Tag.objects.create(
            topic = self.topic_wf,
            chunk = self.chunk_transcript_one,
            topic_present = False
        )
        # Transcript Two Related Elements
        self.chunk_transcript_two = Chunk.objects.create(
            transcript = self.transcript_two,
            chunk_text = self.transcript_two.transcript_text
        )
        self.tag_topic_it_transcript_two = Tag.objects.create(
            topic = self.topic_it,
            chunk = self.chunk_transcript_two,
            topic_present = True,
            relevant_section = "text about IT"
        )
        self.tag_topic_wf_transcript_two = Tag.objects.create(
            topic = self.topic_wf,
            chunk = self.chunk_transcript_two,
            topic_present = False
        )
        
    def testViewTranscriptChunks(self):
        # Call view
        url = reverse('transcription:view_transcript', args=[self.transcript_one.pk])
        response = self.client.get(url)

        # Validate backend interaction worked
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcription/view_transcript.html')

        # Contains the correct HTML elements
        ## analyze-audio-page-section-root
        self.assertContains(response, 'id="view-transcript-chunks-page-section-root"')
        self.assertContains(response, 'id="view-transcript-chunks-page-section-root"')

        # Initial Payload contains the Correct Data
        ## Only Dummy Transcript One
        ## Only tags for a single transcript