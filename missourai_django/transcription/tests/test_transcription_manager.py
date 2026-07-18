from unittest.mock import Mock

from django.test import SimpleTestCase

from transcription.transcription_utils.transcription_manager import (
    TranscriptionManager,
    TranscriptionMediaError,
)


class TranscribeRangeRegressionTests(SimpleTestCase):
    def make_manager(self):
        manager = TranscriptionManager.__new__(TranscriptionManager)
        manager.job_metric = None
        manager.max_split_depth = 0
        manager.min_chunk_duration_sec = 15
        manager.issue_marker_template = (
            "[Transcription warning: audio from {start} to {end} "
            "could not be processed automatically.]"
        )
        manager._cleanup_chunk = Mock()
        return manager

    def test_successful_range_returns_transcript_and_cleans_up_chunk(self):
        manager = self.make_manager()
        manager.read_audio_chunk = Mock(return_value=("chunk.wav", 0.25))
        manager._file_size = Mock(return_value=1024)
        manager._transcribe_chunk_file = Mock(return_value="transcribed text")

        result = manager._transcribe_range_with_fallback(
            start_time=0,
            duration=30,
            chunk_index=1,
        )

        self.assertEqual(result, "transcribed text")
        manager._cleanup_chunk.assert_called_once_with("chunk.wav")

    def test_media_failure_returns_issue_marker_and_cleans_up_chunk(self):
        manager = self.make_manager()
        manager.read_audio_chunk = Mock(
            side_effect=TranscriptionMediaError("Could not extract audio")
        )

        result = manager._transcribe_range_with_fallback(
            start_time=0,
            duration=30,
            chunk_index=1,
        )

        self.assertIn("audio from 00:00:00 to 00:00:30", result)
        manager._cleanup_chunk.assert_called_once_with(None)
