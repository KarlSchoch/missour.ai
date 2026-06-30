import json
import tempfile
import uuid
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.conf import settings

from transcription.models import BackgroundJob, Chunk, Tag, Topic, Transcript
from transcription.tasks import transcribe_uploaded_audio
from transcription.views import _save_upload_for_background_job

User = get_user_model()


class JsonScriptParser(HTMLParser):
    def __init__(self, element_id):
        super().__init__()
        self.element_id = element_id
        self.in_target_element = False
        self.data = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if (
            tag == "script"
            and attrs.get("id") == self.element_id
            and not self.data
        ):
            self.in_target_element = True

    def handle_endtag(self, tag):
        if tag == "script" and self.in_target_element:
            self.in_target_element = False

    def handle_data(self, data):
        if self.in_target_element:
            self.data += data

def get_json_script_payload(response, element_id):
    parser = JsonScriptParser(element_id)
    parser.feed(response.content.decode())
    if not parser.data:
        raise AssertionError(f"Could not find JSON script element with id {element_id}")
    return json.loads(parser.data)


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

def create_topic(
        topic: str,
        description: str,
        user: User
):
    return Topic.objects.create(
        topic = topic,
        description = description,
        created_by = user
    )

class UserScopedTopicTests(TestCase):
    """
    Ensures that topics are scoped to a specific user
    """
    def test_single_user_topics_upload_audio_page(self):
        """
        For the upload_audio.html template, only show topics created by the logged in user
        """
        # Create users and log in
        logged_in_user = User.objects.create_user(
            username='logged-in',
            password='pw1'
        )
        other_user = User.objects.create_user(
            username='other',
            password='pw2'
        )
        self.client.force_login(logged_in_user)
        # Create topic entries for each user
        own_topic = create_topic(
            'Logged in User Upload Topic',
            'Topic created by logged in user',
            logged_in_user
        )
        other_user_topic = create_topic(
            'Other User Upload Topic',
            'Topic created by other user',
            other_user
        )

        response = self.client.get(reverse('transcription:upload_audio'))
        self.assertEqual(response.status_code, 200)

        # Extract the payload rendered by analyze-audio-page-section.html
        initial_payload = get_json_script_payload(
            response,
            "initial-payload-analyze-audio-page-section",
        )

        # Validate that the payload contains only the logged in user's topics
        self.assertEqual(
            initial_payload["topics"],
            [{"value": own_topic.topic, "label": own_topic.topic}],
        )
        self.assertNotIn(
            other_user_topic.topic,
            {topic["value"] for topic in initial_payload["topics"]},
        )

    def test_single_user_topic_list(self):
        """
        For the view_topics.html template, only show topics that are from a single user
        """
        # Create users and log in
        logged_in_user = User.objects.create_user(
            username='logged-in', 
            password='pw1'
        )
        other_user = User.objects.create_user(
            username='other', 
            password='pw2'
        )
        self.client.force_login(logged_in_user)
        # Create topic entries for each user
        own_topic = create_topic(
            'Logged in User Topic',
            'Topic created by logged in user',
            logged_in_user
        )
        other_user_topic = create_topic(
            'Other User Topic',
            'Topic created by other user',
            other_user
        )
    
        response = self.client.get(reverse('api:topic-list'))
        self.assertEqual(response.status_code, 200)

        # Extract returned content from api
        data = response.json()
        returned_topic_ids = {item['id'] for item in data}

        # Validate that you received the logged in user's topics
        self.assertIn(own_topic.id, returned_topic_ids)

        # Validate that the other user's topic is not visible to the logged in user
        self.assertNotIn(other_user_topic.id, returned_topic_ids)

class UserScopedTranscriptTests(TestCase):
    """
    Ensures that transcripts are scoped to a specific user
    """
    def test_single_user_transcript_list(self):
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
        # Create transcript records for each user
        create_transcript('logged in user transcript', 'some text', self.logged_in_user)
        create_transcript('other user transcript', 'some text', self.other_user)
        # Get page, validate you only see a single user's transcript
        response = self.client.get(reverse('transcription:transcripts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'logged in user transcript')
        self.assertNotContains(response, 'other user transcript')
    
    def test_forbidden_transcript(self):
        """
        User gets a 403 Forbidden error if they try to access another user's transcript
        """
        # Create users
        owner = User.objects.create_user(
            username='logged-in', 
            password='pw1'
        )
        intruder = User.objects.create_user(
            username='other', 
            password='pw2'
        )
        self.client.force_login(intruder)
        # Create transcript records for each user
        transcript = create_transcript('other user transcript', 'some text', owner)
        # Get page, validate you only see a single user's transcript
        response = self.client.get(
            reverse(
                'transcription:view_transcript', 
                args=[transcript.pk]
            )
        )
        self.assertEqual(response.status_code, 403)


class AddTaskDemoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="add-user", password="pw")
        self.client.force_login(self.user)

    def test_add_task_submit_page_renders_form(self):
        response = self.client.get(reverse("transcription:add_task_submit"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcription/add_task_submit.html")
        self.assertContains(response, "Add two numbers")
        self.assertContains(response, 'name="x"')
        self.assertContains(response, 'name="y"')

    @patch("transcription.views.add")
    def test_add_task_submit_queues_task_and_redirects_to_result_page(self, mock_add):
        task_id = uuid.uuid4()
        mock_add.delay.return_value.id = str(task_id)

        response = self.client.post(
            reverse("transcription:add_task_submit"),
            data={"x": "2", "y": "3"},
        )

        mock_add.delay.assert_called_once_with(2, 3)
        job = BackgroundJob.objects.get(task_id=str(task_id))
        self.assertEqual(job.created_by, self.user)
        self.assertEqual(job.kind, BackgroundJob.Kind.ADD_DEMO)
        self.assertEqual(job.label, "Add 2 + 3")
        self.assertRedirects(
            response,
            reverse("transcription:add_task_result", args=[job.id]),
            fetch_redirect_response=False,
        )

    @patch("transcription.views.AsyncResult")
    def test_add_task_result_page_uses_job_task_id_to_load_result(self, mock_async_result):
        task_id = uuid.uuid4()
        job = BackgroundJob.objects.create(
            created_by=self.user,
            task_id=str(task_id),
            kind=BackgroundJob.Kind.ADD_DEMO,
            label="Add 2 + 3",
        )

        class FakeAsyncResult:
            status = "SUCCESS"
            result = 5

            def ready(self):
                return True

            def successful(self):
                return True

            def failed(self):
                return False

        mock_async_result.return_value = FakeAsyncResult()

        response = self.client.get(
            reverse("transcription:add_task_result", args=[job.id])
        )

        mock_async_result.assert_called_once_with(str(task_id))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcription/add_task_result.html")
        self.assertContains(response, "Job: Add 2 + 3")
        self.assertContains(response, "Status: SUCCESS")
        self.assertContains(response, "Result: 5")

    def test_add_task_result_page_rejects_other_users_job(self):
        other_user = User.objects.create_user(username="other-add-user", password="pw")
        job = BackgroundJob.objects.create(
            created_by=other_user,
            task_id=str(uuid.uuid4()),
            kind=BackgroundJob.Kind.ADD_DEMO,
            label="Other user's add job",
        )

        response = self.client.get(
            reverse("transcription:add_task_result", args=[job.id])
        )

        self.assertEqual(response.status_code, 404)

    @patch("transcription.views.AsyncResult")
    def test_celery_task_status_returns_owned_task_status(self, mock_async_result):
        task_id = uuid.uuid4()
        BackgroundJob.objects.create(
            created_by=self.user,
            task_id=str(task_id),
            kind=BackgroundJob.Kind.ADD_DEMO,
            label="Add 2 + 3",
        )

        class FakeAsyncResult:
            status = "STARTED"

            def ready(self):
                return False

            def successful(self):
                return False

            def failed(self):
                return False

        mock_async_result.return_value = FakeAsyncResult()

        response = self.client.get(
            reverse("transcription:celery_task_status", args=[task_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "task_id": str(task_id),
                "status": "STARTED",
                "ready": False,
                "successful": False,
                "failed": False,
            },
        )

    def test_celery_task_status_rejects_other_users_task(self):
        other_user = User.objects.create_user(username="other-task-user", password="pw")
        task_id = uuid.uuid4()
        BackgroundJob.objects.create(
            created_by=other_user,
            task_id=str(task_id),
            kind=BackgroundJob.Kind.ADD_DEMO,
            label="Other user's add job",
        )

        response = self.client.get(
            reverse("transcription:celery_task_status", args=[task_id])
        )

        self.assertEqual(response.status_code, 404)

class ViewTranscriptTests(TestCase):
    def setUp(self):
        # Authentication
        self.user = User.objects.create_user(username='test', password='pw')
        self.client.force_login(self.user)
        # Base Records
        self.transcript_one = Transcript.objects.create(
            name = "Dummy Transcript One",
            transcript_text = "Here is some dummy text about IT that should show up",
            created_by = self.user,
        )
        self.transcript_two = Transcript.objects.create(
            name = "Dummy Transcript Two",
            transcript_text = "Here is some dummy text about IT that should NOT show up",
            created_by = self.user,
        )
        self.topic_it = Topic.objects.create(
            topic = "Information Technology",
            description = "",
            created_by = self.user,
        )
        self.topic_wf = Topic.objects.create(
            topic = "Workforce Training",
            description = "",
            created_by = self.user,
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
        self.assertContains(
            response,
            'id="initial-payload-view-transcript-chunks-page-section"',
        )

        # Initial Payload contains the Correct Data
        initial_payload = get_json_script_payload(
            response,
            "initial-payload-view-transcript-chunks-page-section",
        )["rows"]

        ## Tags contain chunks from single transcript (Dummy Transcript One)
        chunks = list( { x['chunk_id'] for x in initial_payload } )
        transcripts = Chunk.objects.filter(pk__in = chunks).values()
        self.assertEqual(len(transcripts), 1)
        trancript_name = Transcript.objects.filter(
            pk = transcripts[0]['transcript_id']
        ).values('name')
        self.assertEqual(trancript_name[0]['name'], self.transcript_one.name)

    @patch("transcription.views.TaggingManager")
    def test_view_transcript_post_does_not_use_other_user_topics(
        self,
        mock_tagging_manager,
    ):
        other_user = User.objects.create_user(username="other", password="pw")
        other_topic = Topic.objects.create(
            topic="Other User View Topic",
            description="",
            created_by=other_user,
        )
        url = reverse('transcription:view_transcript', args=[self.transcript_one.pk])

        response = self.client.post(
            url,
            data={"topics": json.dumps([other_topic.topic])},
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_tagging_manager.call_args.kwargs
        self.assertEqual(call_kwargs["topics"], [])


class UploadAudioTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="upload-user", password="pw")
        self.other_user = User.objects.create_user(username="other-user", password="pw")
        self.client.force_login(self.user)
        self.url = reverse("transcription:upload_audio")
        self.topic = Topic.objects.create(
            topic="Information Technology",
            description="",
            created_by=self.user,
        )
        self.other_topic = Topic.objects.create(
            topic="Other User Topic",
            description="",
            created_by=self.other_user,
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

    def test_save_upload_for_background_job_creates_storage_directory(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile(
                    "audio.mp3",
                    b"fake media payload",
                    content_type="audio/mpeg",
                )

                storage_name = _save_upload_for_background_job(upload)

                self.assertTrue(storage_name.startswith("background_uploads/"))
                self.assertTrue(default_storage.exists(storage_name))
                with default_storage.open(storage_name, "rb") as stored_file:
                    self.assertEqual(stored_file.read(), b"fake media payload")

    @patch("transcription.views.transcribe_uploaded_audio")
    @patch("transcription.views._save_upload_for_background_job")
    @patch("transcription.views.celery_uuid")
    def test_upload_audio_queues_transcription_job(
        self,
        mock_celery_uuid,
        mock_save_upload,
        mock_transcribe_task,
    ):
        task_id = uuid.uuid4()
        mock_celery_uuid.return_value = str(task_id)
        mock_save_upload.return_value = "background_uploads/test-upload.mp4"
        temp_upload = self._make_temp_uploaded_file()

        response = self.client.post(
            self.url,
            data={
                "name": "Large Upload",
                "audio_file": temp_upload,
                "topics": json.dumps([self.topic.topic]),
            },
        )

        job = BackgroundJob.objects.get(task_id=str(task_id))
        self.assertEqual(job.created_by, self.user)
        self.assertEqual(job.kind, BackgroundJob.Kind.TRANSCRIPTION)
        self.assertEqual(job.label, "Transcribe Large Upload")
        self.assertIsNone(job.related_object_id)
        self.assertRedirects(
            response,
            reverse("transcription:transcription_job_result", args=[job.id]),
            fetch_redirect_response=False,
        )
        mock_transcribe_task.apply_async.assert_called_once_with(
            args=[
                job.id,
                "background_uploads/test-upload.mp4",
                "Large Upload",
                [self.topic.id],
            ],
            task_id=str(task_id),
        )

    @patch("transcription.views._save_upload_for_background_job")
    def test_upload_audio_rejects_unknown_topics(
        self,
        mock_save_upload,
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
            status_code=400,
        )
        self.assertFalse(BackgroundJob.objects.filter(label="Transcribe Topic Failure").exists())
        mock_save_upload.assert_not_called()

    @patch("transcription.views._save_upload_for_background_job")
    def test_upload_audio_rejects_other_user_topic(
        self,
        mock_save_upload,
    ):
        upload = SimpleUploadedFile(
            "audio.mp3",
            b"not real audio",
            content_type="audio/mpeg",
        )

        response = self.client.post(
            self.url,
            data={
                "name": "Other Topic Failure",
                "audio_file": upload,
                "topics": json.dumps([self.other_topic.topic]),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "One or more selected topics could not be found.",
            status_code=400,
        )
        self.assertFalse(
            BackgroundJob.objects.filter(label="Transcribe Other Topic Failure").exists()
        )
        mock_save_upload.assert_not_called()

    @patch("transcription.views.AsyncResult")
    def test_transcription_job_result_links_to_created_transcript(
        self,
        mock_async_result,
    ):
        transcript = Transcript.objects.create(
            name="Ready Transcript",
            transcript_text="mock transcript",
            created_by=self.user,
        )
        job = BackgroundJob.objects.create(
            created_by=self.user,
            task_id=str(uuid.uuid4()),
            kind=BackgroundJob.Kind.TRANSCRIPTION,
            label="Transcribe Ready Transcript",
            related_object_id=transcript.id,
        )

        class FakeAsyncResult:
            status = "SUCCESS"

            def successful(self):
                return True

            def failed(self):
                return False

        mock_async_result.return_value = FakeAsyncResult()

        response = self.client.get(
            reverse("transcription:transcription_job_result", args=[job.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcription/transcription_job_result.html")
        self.assertContains(response, "Your transcript is ready.")
        self.assertContains(
            response,
            reverse("transcription:view_transcript", args=[transcript.id]),
        )

    def test_transcription_job_result_rejects_other_users_job(self):
        other_user = User.objects.create_user(username="other-job-user", password="pw")
        job = BackgroundJob.objects.create(
            created_by=other_user,
            task_id=str(uuid.uuid4()),
            kind=BackgroundJob.Kind.TRANSCRIPTION,
            label="Other user's transcription job",
        )

        response = self.client.get(
            reverse("transcription:transcription_job_result", args=[job.id])
        )

        self.assertEqual(response.status_code, 404)


class TranscribeUploadedAudioTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="task-user", password="pw")
        self.topic = Topic.objects.create(
            topic="Information Technology",
            description="",
            created_by=self.user,
        )
        self.job = BackgroundJob.objects.create(
            created_by=self.user,
            task_id=str(uuid.uuid4()),
            kind=BackgroundJob.Kind.TRANSCRIPTION,
            label="Transcribe Task Upload",
        )

    @patch("transcription.tasks.TaggingManager")
    @patch("transcription.tasks.process_audio", return_value="mock transcript")
    @patch("transcription.tasks.default_storage")
    def test_task_creates_transcript_updates_job_and_deletes_upload(
        self,
        mock_storage,
        _mock_process_audio,
        mock_tagging_manager,
    ):
        mock_storage.path.return_value = "stored-upload.mp4"
        mock_storage.exists.return_value = True

        transcript_id = transcribe_uploaded_audio(
            self.job.id,
            "background_uploads/test-upload.mp4",
            "Task Upload",
            [self.topic.id],
        )

        transcript = Transcript.objects.get(id=transcript_id)
        self.assertEqual(transcript.name, "Task Upload")
        self.assertEqual(transcript.transcript_text, "mock transcript")
        self.assertEqual(transcript.created_by, self.user)
        self.job.refresh_from_db()
        self.assertEqual(self.job.related_object_id, transcript.id)
        mock_tagging_manager.return_value.tag_transcript.assert_called_once_with()
        mock_storage.delete.assert_called_once_with(
            "background_uploads/test-upload.mp4"
        )

    @patch("transcription.tasks.process_audio", return_value="mock transcript")
    @patch("transcription.tasks.default_storage")
    def test_task_rejects_topics_not_owned_by_job_user(
        self,
        mock_storage,
        _mock_process_audio,
    ):
        other_user = User.objects.create_user(username="other-topic-owner", password="pw")
        other_topic = Topic.objects.create(
            topic="Other User Topic",
            description="",
            created_by=other_user,
        )
        mock_storage.path.return_value = "stored-upload.mp4"
        mock_storage.exists.return_value = True

        with self.assertRaises(ValueError):
            transcribe_uploaded_audio(
                self.job.id,
                "background_uploads/test-upload.mp4",
                "Task Upload",
                [other_topic.id],
            )

        self.assertFalse(Transcript.objects.filter(name="Task Upload").exists())
        mock_storage.delete.assert_called_once_with(
            "background_uploads/test-upload.mp4"
        )

    @patch("transcription.tasks.TaggingManager")
    @patch("transcription.tasks.process_audio", return_value="mock transcript")
    @patch("transcription.tasks.default_storage")
    def test_task_rolls_back_transcript_when_tagging_fails(
        self,
        mock_storage,
        _mock_process_audio,
        mock_tagging_manager,
    ):
        mock_storage.path.return_value = "stored-upload.mp4"
        mock_storage.exists.return_value = True
        mock_tagging_manager.return_value.tag_transcript.side_effect = RuntimeError(
            "boom"
        )

        with self.assertRaises(RuntimeError):
            transcribe_uploaded_audio(
                self.job.id,
                "background_uploads/test-upload.mp4",
                "Task Upload",
                [self.topic.id],
            )

        self.assertFalse(Transcript.objects.filter(name="Task Upload").exists())
        self.job.refresh_from_db()
        self.assertIsNone(self.job.related_object_id)
        mock_storage.delete.assert_called_once_with(
            "background_uploads/test-upload.mp4"
        )
