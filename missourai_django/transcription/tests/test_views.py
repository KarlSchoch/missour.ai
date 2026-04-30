import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.conf import settings

from transcription.models import Chunk, Tag, Topic, Transcript

User = get_user_model()

def create_transcript(
        name: str,
        text: str,
        user: User
    ):
    return Transcript.objects.create(
        name = name,
        transcript_text = text,
        created_by = user
    )

class UserScopedContentTests(TestCase):
    """
    Ensures that content is scoped to a specific user
    """
    def singleUserTranscriptList(self):
        """
        Only show transcripts that were created by the logged in user
        """
        # Create users
        self.logged_in_user = User.objects.create_user(
            username='logged-in', 
            password='pw1'
        )
        self.other_user = User.objects.create_user(
            username='other', 
            password='pw2'
        )
        self.client.force_login(self.logged_in_user)
        # Create transcript records for each usre
        user_question = create_transcript('logged in user transcript', 'some text', self.logged_in_user)
        other_user_question = create_transcript('other user transcript', 'some text', self.logged_in_user)
        # Get page, validate you only see a single user's transcript
        response = self.client.get(reverse('transcription:transcripts'))
        self.assertEqual(response.status_code)
        self.assertContains()

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
        self.assertContains(response, 'id="view-transcript-chunks-page-section-root"')
        self.assertContains(response, 'id="initial-payload"')

        # Initial Payload contains the Correct Data
        initial_payload = response.context["initial_payload"]

        ## Tags contain chunks from single transcript (Dummy Transcript One)
        chunks = list( { x['chunk_id'] for x in initial_payload } )
        transcripts = Chunk.objects.filter(pk__in = chunks).values()
        self.assertEqual(len(transcripts), 1)
        trancript_name = Transcript.objects.filter(
            pk = transcripts[0]['transcript_id']
        ).values('name')
        self.assertEqual(trancript_name[0]['name'], self.transcript_one.name)


class UploadAudioTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="upload-user", password="pw")
        self.client.force_login(self.user)
        self.url = reverse("transcription:upload_audio")
        self.topic = Topic.objects.create(
            topic="Information Technology",
            description="",
        )

    def _make_temp_uploaded_file(self, content=b"fake media payload"):
        uploaded_file = TemporaryUploadedFile(
            name="large-video.mp4",
            content_type="video/mp4",
            size=len(content),
            charset=None,
        )
        uploaded_file.write(content)
        uploaded_file.seek(0)
        return uploaded_file

    @patch("transcription.views.TaggingManager")
    @patch("transcription.views.process_audio", return_value="mock transcript")
    def test_upload_audio_accepts_temporary_uploaded_file(
        self,
        mock_process_audio,
        mock_tagging_manager,
    ):
        temp_upload = self._make_temp_uploaded_file()

        response = self.client.post(
            self.url,
            data={
                "name": "Large Upload",
                "audio_file": temp_upload,
                "topics": json.dumps([self.topic.topic]),
            },
        )

        self.assertRedirects(response, reverse("transcription:transcripts"))
        mock_process_audio.assert_called_once_with(temp_upload.temporary_file_path())
        mock_tagging_manager.return_value.tag_transcript.assert_called_once_with()
        self.assertTrue(
            Transcript.objects.filter(
                name="Large Upload",
                transcript_text="mock transcript",
            ).exists()
        )

    @patch("transcription.views.process_audio", side_effect=RuntimeError("boom"))
    def test_upload_audio_returns_form_error_for_unexpected_transcription_failure(
        self,
        _mock_process_audio,
    ):
        upload = SimpleUploadedFile(
            "audio.mp3",
            b"not real audio",
            content_type="audio/mpeg",
        )

        response = self.client.post(
            self.url,
            data={"name": "Broken Upload", "audio_file": upload, "topics": "[]"},
        )

        self.assertEqual(response.status_code, 500)
        self.assertContains(
            response,
            "Something went wrong while transcribing the uploaded file.",
        )
        self.assertFalse(Transcript.objects.filter(name="Broken Upload").exists())

    @patch("transcription.views.process_audio", return_value="mock transcript")
    def test_upload_audio_rejects_unknown_topics(
        self,
        _mock_process_audio,
    ):
        upload = SimpleUploadedFile(
            "audio.mp3",
            b"not real audio",
            content_type="audio/mpeg",
        )

        response = self.client.post(
            self.url,
            data={
                "name": "Topic Failure",
                "audio_file": upload,
                "topics": json.dumps([self.topic.topic, "Unknown Topic"]),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "One or more selected topics could not be found.",
        )
        self.assertFalse(Transcript.objects.filter(name="Topic Failure").exists())

    @patch("transcription.views.TaggingManager")
    @patch("transcription.views.process_audio", return_value="mock transcript")
    def test_upload_audio_rolls_back_transcript_when_tagging_fails(
        self,
        _mock_process_audio,
        mock_tagging_manager,
    ):
        mock_tagging_manager.return_value.tag_transcript.side_effect = RuntimeError("boom")
        upload = SimpleUploadedFile(
            "audio.mp3",
            b"not real audio",
            content_type="audio/mpeg",
        )

        response = self.client.post(
            self.url,
            data={
                "name": "Tag Failure",
                "audio_file": upload,
                "topics": json.dumps([self.topic.topic]),
            },
        )

        self.assertEqual(response.status_code, 500)
        self.assertContains(
            response,
            "Something went wrong while tagging the transcript.",
        )
        self.assertFalse(Transcript.objects.filter(name="Tag Failure").exists())
