from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call

from django.contrib.auth import get_user_model
from django.test import TestCase

from transcription.models import (
    BackgroundJob,
    ModelPrice,
    TaskPricing,
    Transcript,
    TranscriptionChunkMetric,
    TranscriptionJobMetric,
    UsageEvent,
)
from transcription.services.pricing import PricingResolutionError
from transcription.transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError,
)


class CreateTranscriptTests(TestCase):
    model_name = "transcription-manager-test-model"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="transcription-manager-user"
        )

    def setUp(self):
        super().setUp()
        self.transcript = Transcript.objects.create(
            name="Transcription manager transcript",
            transcript_text="",
            created_by=self.user,
        )
        self.background_job = BackgroundJob.objects.create(
            created_by=self.user,
            task_id=f"transcription-task-{self.transcript.pk}",
            kind=BackgroundJob.Kind.TRANSCRIPTION,
            label="Test transcription",
            related_object_id=self.transcript.pk,
        )
        self.job_metric = TranscriptionJobMetric.objects.create(
            background_job=self.background_job,
            transcript=self.transcript,
            model_name=self.model_name,
        )
        self.model_price = ModelPrice.objects.create(
            provider=ModelPrice.Provider.OPENAI,
            model_name=self.model_name,
            billing_unit=ModelPrice.BillingUnit.AUDIO_DURATION,
            rate_per_minute=Decimal("0.60"),
            currency="USD",
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        self.task_pricing = TaskPricing.objects.create(
            task_type=TaskPricing.TaskType.TRANSCRIPTION,
            model_price=self.model_price,
            multiplier=Decimal("1.0"),
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

    def make_manager(self, *, model_name=None, chunk_count=1):
        manager = TranscriptionManager.__new__(TranscriptionManager)
        manager.job_metric = self.job_metric
        manager.model_name = model_name or self.model_name
        manager.file_duration = chunk_count * 10
        manager.chunk_length_sec = 10
        manager.max_concurrent_chunks = 1
        manager.max_split_depth = 0
        manager.min_chunk_duration_sec = 15
        manager.issue_marker_template = (
            "[Transcription warning: audio from {start} to {end} "
            "could not be processed automatically.]"
        )
        manager.normalized_audio_path = "normalized.wav"
        manager._cleanup_chunk = Mock()
        manager._cleanup_normalized_audio = Mock()
        manager.read_audio_chunk = Mock(
            side_effect=[(f"chunk-{index}.wav", 0.25) for index in range(chunk_count)]
        )
        manager._file_size = Mock(return_value=1024)
        manager._submitted_audio_duration = Mock(return_value=10)
        manager._transcribe_chunk_file = Mock()
        return manager

    def test_successful_ranges_return_transcript_cleanup_and_create_usage_per_chunk(self):
        manager = self.make_manager(chunk_count=2)
        manager._transcribe_chunk_file.side_effect = [
            SimpleNamespace(text="first chunk", id="request-1"),
            SimpleNamespace(text="second chunk", id="request-2"),
        ]

        result = manager.create_transcript()

        # Validate that the transcript is created
        self.assertEqual(result, "first chunk\nsecond chunk")
        # Validate that all the intermediate files are deleted
        self.assertEqual(
            manager._cleanup_chunk.call_args_list,
            [call("chunk-0.wav"), call("chunk-1.wav")],
        )
        manager._cleanup_normalized_audio.assert_called_once_with()
        # Validate the UsageEvents
        events = UsageEvent.objects.filter(transcript=self.transcript).order_by(
            "transcription_chunk__chunk_index"
        )
        ## One usage event created per chunk
        self.assertEqual(events.count(), 2)
        ## All usage events succeed
        self.assertFalse(events.exclude(status=UsageEvent.Status.SUCCEEDED).exists())
        ## Specific field
        self.assertEqual(
            list(events.values_list("provider_request_id", flat=True)),
            ["request-1", "request-2"],
        )
        self.assertEqual(
            list(events.values_list("audio_duration_seconds", flat=True)),
            [Decimal("10.000000"), Decimal("10.000000")],
        )
        self.assertFalse(events.filter(transcription_chunk__isnull=True).exists())
        self.assertEqual(
            TranscriptionChunkMetric.objects.filter(
                job_metric=self.job_metric,
                status=TranscriptionChunkMetric.Status.SUCCESS,
            ).count(),
            2,
        )

    def test_chunk_extraction_error_returns_warning_cleans_up_and_creates_no_usage(self):
        manager = self.make_manager()
        manager.read_audio_chunk.side_effect = TranscriptionMediaError(
            "Could not extract audio"
        )

        result = manager.create_transcript()

        self.assertIn("audio from 00:00:00 to 00:00:10", result)
        manager._cleanup_chunk.assert_called_once_with(None)
        manager._cleanup_normalized_audio.assert_called_once_with()
        # Validate that no UsageEvent was created
        self.assertFalse(UsageEvent.objects.exists())
        # Validate that the logging infrastructure around transcripts was created
        metric = TranscriptionChunkMetric.objects.get(job_metric=self.job_metric)
        self.assertEqual(metric.status, TranscriptionChunkMetric.Status.FAILED)
        self.assertEqual(metric.error_type, "TranscriptionMediaError")

    def test_unexpected_duration_error_propagates_cleans_up_and_creates_no_usage(self):
        manager = self.make_manager()
        manager._submitted_audio_duration.side_effect = RuntimeError(
            "duration calculation failed"
        )

        with self.assertRaisesRegex(RuntimeError, "duration calculation failed"):
            manager.create_transcript()

        # Validate that audio files were cleaned up
        manager._cleanup_chunk.assert_called_once_with("chunk-0.wav")
        manager._cleanup_normalized_audio.assert_called_once_with()
        # Validate that no usage event was created
        self.assertFalse(UsageEvent.objects.exists())
        # Validate that no API calls were made (proxy - this is the wrapper function)
        manager._transcribe_chunk_file.assert_not_called()

    def test_api_failure_propagates_and_marks_usage_event_failed(self):
        manager = self.make_manager()
        manager._transcribe_chunk_file.side_effect = RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            manager.create_transcript()

        # Validate file cleanup
        manager._cleanup_chunk.assert_called_once_with("chunk-0.wav")
        manager._cleanup_normalized_audio.assert_called_once_with()
        # Validate that failure usage event gets created
        event = UsageEvent.objects.get(transcript=self.transcript)
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertIn(
            "provider unavailable",
            event.calculation_details["lifecycle"]["reason"],
        )

    def test_pricing_resolution_failure_propagates_and_creates_no_usage(self):
        manager = self.make_manager(model_name="model-with-no-price")

        with self.assertRaises(PricingResolutionError):
            manager.create_transcript()

        manager._cleanup_chunk.assert_called_once_with("chunk-0.wav")
        manager._cleanup_normalized_audio.assert_called_once_with()
        self.assertFalse(UsageEvent.objects.exists())
        manager._transcribe_chunk_file.assert_not_called()
