import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from transcription.models import Chunk, Tag, Transcript, Topic, Summary

User = get_user_model()
FIXTURE_ROOT = Path(settings.BASE_DIR).parent / "test" / "fixtures" / "api"


def load_fixture(*parts):
    path = FIXTURE_ROOT.joinpath(*parts)
    return json.loads(path.read_text(encoding="utf-8"))


class ApiTopicTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="api-user", password="pw")
        self.client.force_login(self.user)
        self.list_url = reverse("api:topic-list")

    def test_topics_list_matches_fixture(self):
        fixture = load_fixture("topic", "list.json")
        for item in fixture:
            Topic.objects.create(topic=item["topic"], description=item["description"])

        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(sorted(res.json(), key=lambda x: x["id"]), fixture)

    def test_topics_create_from_fixture(self):
        payload = load_fixture("topic", "create.json")

        res = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(res.status_code, 201)
        
        data = res.json()
        self.assertEqual(data["topic"], payload["topic"])
        self.assertEqual(data["description"], payload["description"])
        
        topic = Topic.objects.get(topic=payload["topic"])
        self.assertEqual(topic.description, payload["description"])
        self.assertEqual(topic.created_by, self.user)

    def test_topics_requires_auth(self):
        anon_client = APIClient()

        res = anon_client.get(self.list_url)
        self.assertEqual(res.status_code, 403)


class ApiSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="api-user", password="pw")
        self.client.force_login(self.user)
        self.list_url = reverse("api:summary-list")

        self.transcript = Transcript.objects.create(
            name="Transcript One",
            transcript_text="Transcript text",
        )
        self.other_transcript = Transcript.objects.create(
            name="Transcript Two",
            transcript_text="Other transcript text",
        )
        self.topic = Topic.objects.create(topic="AI", description="Artificial intelligence")

    def test_summaries_list_matches_fixture(self):
        fixture = load_fixture("summary", "list.json")
        Summary.objects.create(
            transcript=self.transcript,
            summary_type=fixture[0]["summary_type"],
            topic=None,
            text=fixture[0]["text"],
        )
        Summary.objects.create(
            transcript=self.transcript,
            summary_type=fixture[1]["summary_type"],
            topic=self.topic,
            text=fixture[1]["text"],
        )

        expected = load_fixture("summary", "list.json")
        expected[0]["transcript"] = self.transcript.id
        expected[1]["transcript"] = self.transcript.id
        expected[1]["topic"] = self.topic.id

        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 200)
        data = sorted(res.json(), key=lambda x: (x["summary_type"], x["text"] or ""))
        expected = sorted(expected, key=lambda x: (x["summary_type"], x["text"] or ""))
        self.assertEqual(data, expected)

    def test_summaries_create_general_from_fixture(self):
        payload = load_fixture("summary", "create_general.json")
        payload["transcript"] = self.transcript.id

        res = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["summary_type"], "general")
        self.assertIsNone(res.json()["topic"])

    def test_summaries_create_topic_from_fixture(self):
        payload = load_fixture("summary", "create_topic.json")
        payload["transcript"] = self.transcript.id
        payload["topic"] = self.topic.id

        res = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["summary_type"], "topic")
        self.assertEqual(res.json()["topic"], self.topic.id)

    def test_summaries_filter_by_transcript(self):
        Summary.objects.create(
            transcript=self.transcript,
            summary_type=Summary.SummaryType.GENERAL,
            topic=None,
            text="Summary for transcript one",
        )
        Summary.objects.create(
            transcript=self.other_transcript,
            summary_type=Summary.SummaryType.GENERAL,
            topic=None,
            text="Summary for transcript two",
        )

        res = self.client.get(f"{self.list_url}?transcript={self.transcript.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["transcript"], self.transcript.id)

    def test_summaries_requires_auth(self):
        anon_client = APIClient()

        res = anon_client.get(self.list_url)
        self.assertEqual(res.status_code, 403)

    def test_summaries_reject_invalid_topic_for_general(self):
        payload = load_fixture("summary", "create_general.json")
        payload["transcript"] = self.transcript.id
        payload["topic"] = self.topic.id

        res = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("topic", res.json())

    def test_summaries_reject_missing_topic_for_topic(self):
        payload = load_fixture("summary", "create_topic.json")
        payload["transcript"] = self.transcript.id
        payload["topic"] = None

        res = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("topic", res.json())


class UserScopedSummaryTests(TestCase):
    """
    Ensures summary creation is scoped to the authenticated user's transcripts
    and topics.
    """

    def setUp(self):
        self.client = APIClient()
        self.logged_in_user = User.objects.create_user(
            username="logged-in",
            password="pw1",
        )
        self.other_user = User.objects.create_user(
            username="other",
            password="pw2",
        )
        self.client.force_login(self.logged_in_user)
        self.list_url = reverse("api:summary-list")

        self.own_transcript = Transcript.objects.create(
            name="Logged In User Transcript",
            transcript_text="Content about the logged in user's topic.",
            created_by=self.logged_in_user,
        )
        self.other_transcript = Transcript.objects.create(
            name="Other User Transcript",
            transcript_text="Content about the other user's topic.",
            created_by=self.other_user,
        )

        self.own_topic = Topic.objects.create(
            topic="Logged In User Topic",
            description="Topic created by logged in user",
            created_by=self.logged_in_user,
        )
        self.other_topic = Topic.objects.create(
            topic="Other User Topic",
            description="Topic created by other user",
            created_by=self.other_user,
        )

        self.own_chunk = Chunk.objects.create(
            transcript=self.own_transcript,
            chunk_text="Content about the logged in user's topic.",
        )
        Tag.objects.create(
            topic=self.own_topic,
            chunk=self.own_chunk,
            topic_present=True,
            relevant_section="Content about the logged in user's topic.",
        )

    def test_create_topic_summary_rejects_own_topic_for_other_user_transcript(self):
        payload = {
            "transcript": self.other_transcript.id,
            "summary_type": "topic",
            "topic": self.own_topic.id,
        }

        res = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(res.status_code, 404)
        self.assertFalse(
            Summary.objects.filter(
                transcript=self.other_transcript,
                topic=self.own_topic,
            ).exists()
        )

    def test_create_topic_summary_rejects_other_user_topic_for_own_transcript(self):
        payload = {
            "transcript": self.own_transcript.id,
            "summary_type": "topic",
            "topic": self.other_topic.id,
        }

        res = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(res.status_code, 404)
        self.assertFalse(
            Summary.objects.filter(
                transcript=self.own_transcript,
                topic=self.other_topic,
            ).exists()
        )

    @patch("transcription.api_views.summary_manager")
    def test_create_topic_summary_allows_own_topic_for_own_transcript(
        self,
        mock_summary_manager,
    ):
        summary = Summary.objects.create(
            transcript=self.own_transcript,
            summary_type=Summary.SummaryType.TOPIC,
            topic=self.own_topic,
            text="Summary for owned topic.",
        )
        mock_summary_manager.summarize.return_value = summary
        payload = {
            "transcript": self.own_transcript.id,
            "summary_type": "topic",
            "topic": self.own_topic.id,
        }

        res = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["transcript"], self.own_transcript.id)
        self.assertEqual(res.json()["topic"], self.own_topic.id)
        mock_summary_manager.summarize.assert_called_once()
