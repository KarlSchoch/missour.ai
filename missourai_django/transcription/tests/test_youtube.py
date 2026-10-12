import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from celery.exceptions import Ignore
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from transcription.models import BackgroundJob, Transcript, Topic, Summary, TranscriptionBillingAttempt, UsageEvent
from transcription.services.transcription_billing import record_transcript_delivery, finalize_transcription_billing
from transcription.tasks import transcribe_youtube, tag_saved_transcript
from transcription.transcription_utils.captions import english_tracks, normalize_json3
from transcription.transcription_utils.sources import SourceError, SourceResult, validate_english_response, validate_video_metadata, youtube_source
from transcription.transcription_utils.transcription_manager import TranscriptionManager
from transcription.transcription_utils.youtube import YouTubeSource

VIDEO = "aircAruvnKk"
URL = f"https://www.youtube.com/watch?v={VIDEO}"


def caption(text, start=0, length=1000, **extra):
    return {"tStartMs": start, "dDurationMs": length, "segs": [{"utf8": text}], **extra}


def metadata(**extra):
    return {"id": VIDEO, "title": "Hearing", "duration": 100,
            "live_status": "not_live", "availability": "public", **extra}


def track(lang="en", **extra):
    return {"ext": "json3", "url": f"https://www.youtube.com/api/timedtext?lang={lang}", **extra}


class SourceTests(SimpleTestCase):
    def test_url_allowlist_and_canonicalization(self):
        for url in [URL, f"https://youtu.be/{VIDEO}?t=12", f"https://m.youtube.com/watch?v={VIDEO}",
                    f"https://www.youtube.com/live/{VIDEO}"]:
            self.assertEqual(youtube_source(url), (VIDEO, URL))
        for url in ["https://evil.test/watch?v=" + VIDEO, "https://youtube.com.evil.test/watch?v=" + VIDEO,
                    "https://youtube.com@127.0.0.1/watch?v=" + VIDEO, URL + "&list=123", "file:///tmp/test",
                    f"https://youtube.com:443/watch?v={VIDEO}", "https://youtube.com/playlist?list=x"]:
            with self.subTest(url=url), self.assertRaises(SourceError):
                youtube_source(url)

    def test_archives_limit_and_ineligible_sources(self):
        self.assertEqual(validate_video_metadata(metadata(duration=28800, live_status="was_live"), 28800), 28800)
        for fields in [{"duration": 28801}, {"duration": None}, {"duration": float("nan")},
                       {"live_status": "is_live"}, {"live_status": "post_live"},
                       {"availability": "private"}, {"age_limit": 18}]:
            with self.subTest(fields=fields), self.assertRaises(SourceError):
                validate_video_metadata(metadata(**fields), 28800)

    def test_creator_preference_variants_and_translation_exclusion(self):
        info = metadata(subtitles={"en-GB": [track("en-GB")], "fr": [track("fr")]},
                        automatic_captions={"en": [track(url="https://www.youtube.com/api/timedtext?lang=fr&tlang=en")],
                                            "en-orig": [track()], "en-US": [track("en-US")]})
        selected = list(english_tracks(info))
        self.assertEqual([item[:2] for item in selected], [
            ("creator_captions", "en-gb"), ("automatic_captions", "en"), ("automatic_captions", "en-us")])

    def test_rolling_updates_and_legitimate_repetition(self):
        text, warnings = normalize_json3({"events": [
            caption("<i>Hello</i> &amp; welcome", length=2000, wWinId=1),
            caption("Hello &amp; welcome everyone", start=1000, length=2000, wWinId=1),
            caption("everyone", start=3000), caption("yes", start=4000), caption("yes", start=5000),
        ]}, 6)
        self.assertEqual(text, "Hello & welcome everyone everyone yes yes")
        self.assertEqual(warnings, [])

    def test_overlapping_manual_cues_preserve_repeated_speech(self):
        text, _ = normalize_json3({"events": [caption("Thank you", length=2000),
            caption("you may proceed", start=1500, length=1000)]}, 3)
        self.assertEqual(text, "Thank you you may proceed")

    def test_append_events_are_new_speech_even_with_repeated_words(self):
        text, _ = normalize_json3({"events": [caption("yes", length=5000, wWinId=1),
            caption("yes", start=1000, length=4000, wWinId=1, aAppend=1)]}, 5)
        self.assertEqual(text, "yes yes")

    def test_same_time_replacement_keeps_final_wording(self):
        text, _ = normalize_json3({"events": [caption("Hello", wWinId=1),
            caption("Hello wrong", wWinId=1), caption("Hello world", wWinId=1)]}, 1)
        self.assertEqual(text, "Hello world")

    def test_gaps_warn_without_rejection_and_bad_captions_fail(self):
        text, warnings = normalize_json3({"events": [caption("Opening", start=301000),
            caption("Closing", start=1000000)]}, 1500)
        self.assertEqual(text, "Opening Closing")
        self.assertEqual(len(warnings), 3)
        for data in [{"events": []}, {"events": [caption("bad", start=-1)]},
                     {"events": [caption("bad", start=200000)]}]:
            with self.assertRaises(SourceError):
                normalize_json3(data, 100)

    def test_detected_language_not_english_output_is_required(self):
        for response in [SimpleNamespace(languages=[{"code": "en"}]), {"language": "english"},
                         {"languages": [{"code": "en-GB"}]}]:
            validate_english_response(response)
        for response in [{"text": "English text"}, {"languages": []}, {"language": "spanish"},
                         {"languages": [{"code": "en"}, {"code": "es"}]}]:
            with self.assertRaises(SourceError):
                validate_english_response(response)

    @override_settings(YOUTUBE_RETRIEVAL_ATTEMPTS=2)
    @patch("transcription.transcription_utils.youtube.time.sleep")
    @patch("transcription.transcription_utils.youtube.subprocess.run")
    def test_retrieval_retries_are_bounded(self, run, sleep):
        run.return_value = SimpleNamespace(returncode=1, stderr="temporary network error")
        with self.assertRaises(SourceError):
            YouTubeSource().retrieve("caption", "https://www.youtube.com/api/timedtext?lang=en")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertIn("timeout", run.call_args.kwargs)


class ManagerSourceTests(SimpleTestCase):
    def test_media_timeout_removes_partial_output(self):
        manager = TranscriptionManager(youtube_url=URL)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "chunk.wav"
            output.write_bytes(b"partial")
            with patch("transcription.transcription_utils.transcription_manager.subprocess.run",
                       side_effect=subprocess.TimeoutExpired("ffmpeg", 1800)) as run:
                with self.assertRaisesRegex(SourceError, "timed out"):
                    manager._run_media(["ffmpeg", "-y", str(output)])
            self.assertFalse(output.exists())
            self.assertEqual(run.call_args.kwargs["timeout"], 1800)

    @patch("transcription.transcription_utils.transcription_manager.OpenAI")
    @patch("transcription.transcription_utils.transcription_manager.subprocess.run")
    @patch("transcription.transcription_utils.transcription_manager.YouTubeSource")
    def test_caption_success_needs_no_audio_or_api_key(self, source, media, client):
        source.return_value.retrieve.side_effect = [metadata(subtitles={"en": [track()]}),
                                                  {"events": [caption("Hello")]}]
        manager = TranscriptionManager(youtube_url=URL)
        result = manager.process_source()
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.provenance, "creator_captions")
        self.assertEqual([c.args[0] for c in source.return_value.retrieve.call_args_list], ["metadata", "caption"])
        media.assert_not_called()
        client.assert_not_called()

    @patch("transcription.transcription_utils.transcription_manager.YouTubeSource")
    def test_unusable_creator_captions_try_automatic_before_audio(self, source):
        source.return_value.retrieve.side_effect = [metadata(subtitles={"en": [track()]},
            automatic_captions={"en": [track()]}), {"events": []}, {"events": [caption("Automatic")]}]
        result = TranscriptionManager(youtube_url=URL).process_source()
        self.assertEqual(result.provenance, "automatic_captions")
        self.assertTrue(result.retrieval_errors)

    @patch("transcription.transcription_utils.transcription_manager.YouTubeSource")
    def test_audio_fallback_reuses_pipeline_and_cleans_downloads(self, source):
        directory = []
        def retrieve(operation, url, folder=None):
            if operation == "metadata":
                return metadata()
            directory.append(folder)
            path = Path(folder) / "audio.webm"
            path.write_bytes(b"audio")
            return {"path": str(path)}
        source.return_value.retrieve.side_effect = retrieve
        manager = TranscriptionManager(api_key="test", youtube_url=URL)
        with patch.object(manager, "_prepare_audio") as prepare, patch.object(manager, "_create_audio_transcript", return_value="English speech") as transcribe:
            result = manager.process_source()
        self.assertEqual(result.provenance, "audio_transcription")
        prepare.assert_called_once()
        transcribe.assert_called_once()
        self.assertFalse(Path(directory[0]).exists())

    @patch("transcription.transcription_utils.transcription_manager.YouTubeSource")
    def test_audio_failure_cleans_downloads(self, source):
        folders = []
        def retrieve(operation, url, folder=None):
            if operation == "metadata":
                return metadata()
            folders.append(folder)
            path = Path(folder) / "audio.webm"
            path.write_bytes(b"audio")
            return {"path": str(path)}
        source.return_value.retrieve.side_effect = retrieve
        manager = TranscriptionManager(api_key="test", youtube_url=URL)
        with patch.object(manager, "_prepare_audio", side_effect=SourceError("failure")):
            with self.assertRaises(SourceError):
                manager.process_source()
        self.assertFalse(Path(folders[0]).exists())

    @override_settings(TRANSCRIPTION_MODEL="gpt-transcribe")
    @patch.dict(os.environ, {"MODEL_ENV": "test"})
    @patch("transcription.transcription_utils.transcription_manager.YouTubeSource")
    def test_real_ffmpeg_normalization_and_chunks_share_upload_pipeline(self, source):
        folders = []
        def retrieve(operation, url, folder=None):
            if operation == "metadata":
                return metadata(duration=1)
            folders.append(folder)
            path = str(Path(folder) / "audio.wav")
            with wave.open(path, "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b"\0" * 32000)
            return {"path": path}
        source.return_value.retrieve.side_effect = retrieve
        manager = TranscriptionManager(api_key="test", youtube_url=URL)
        normalized_paths = []
        chunk_paths = []
        def transcription(chunk_path):
            chunk_paths.append(chunk_path)
            normalized_paths.append(manager.normalized_audio_path)
            with wave.open(chunk_path, "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getframerate(), 16000)
                self.assertEqual(audio.getsampwidth(), 2)
            return SimpleNamespace(text="Verified English speech", languages=[{"code": "en"}])
        with patch.object(manager, "_transcribe_chunk_file", side_effect=transcription):
            result = manager.process_source()
        self.assertEqual(result.text, "Verified English speech")
        self.assertTrue(chunk_paths)
        self.assertTrue(all(not Path(path).exists() for path in chunk_paths + normalized_paths + folders))


class YouTubeWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="youtube-user")
        self.other = get_user_model().objects.create_user(username="youtube-other")
        self.client.force_login(self.user)
        self.url = reverse("transcription:submit_youtube")

    def submit(self, **fields):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, {"youtube_url": URL, "authorized": True, **fields})

    @patch("transcription.views.transcribe_youtube")
    def test_submit_deduplicates_per_user_and_requires_authorization(self, task):
        self.assertEqual(self.client.post(self.url, {"youtube_url": URL}).status_code, 400)
        self.assertFalse(Transcript.objects.exists())
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(Transcript.objects.count(), 1)
        self.assertEqual(task.apply_async.call_count, 1)
        self.client.force_login(self.other)
        self.submit()
        self.assertEqual(Transcript.objects.count(), 2)
        self.assertEqual(task.apply_async.call_count, 2)

    @patch("transcription.views.transcribe_youtube")
    @patch("transcription.views.tag_saved_transcript")
    def test_completed_transcript_reuses_text_for_new_topics(self, tag, transcribe):
        saved = Transcript.objects.create(created_by=self.user, name="Saved", source_type="youtube", video_id=VIDEO,
            source_url=URL, source_status="ready", transcript_text="Saved English text")
        topic = Topic.objects.create(created_by=self.user, topic="New topic")
        self.submit(topics=json.dumps([topic.topic]))
        transcribe.apply_async.assert_not_called()
        tag.apply_async.assert_called_once()
        saved.refresh_from_db()
        self.assertEqual(saved.transcript_text, "Saved English text")

    @patch("transcription.views.transcribe_youtube")
    def test_failed_submission_requires_explicit_retry(self, task):
        topic = Topic.objects.create(created_by=self.user, topic="Retry topic")
        self.submit(topics=json.dumps([topic.topic]))
        saved = Transcript.objects.get()
        saved.source_status = "failed"
        saved.save()
        self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(task.apply_async.call_count, 1)
        self.assertEqual(self.submit(retry=True).status_code, 302)
        self.assertEqual(task.apply_async.call_count, 2)
        self.assertEqual(task.apply_async.call_args.kwargs["args"][2], [topic.pk])
        self.assertEqual(TranscriptionBillingAttempt.objects.count(), 2)

    def make_job(self):
        transcript = Transcript.objects.create(created_by=self.user, name=VIDEO, video_id=VIDEO,
            source_url=URL, source_type="youtube")
        job = BackgroundJob.objects.create(created_by=self.user, task_id="source-test", kind="transcription",
            related_object_id=transcript.pk)
        attempt = TranscriptionBillingAttempt.objects.create(background_job=job, transcript=transcript)
        return transcript, job, attempt

    @patch("transcription.tasks.TaggingManager")
    @patch("transcription.tasks.TranscriptionManager")
    def test_caption_delivery_zero_usage_and_duplicate_task_does_no_work(self, manager, tagging):
        transcript, job, attempt = self.make_job()
        manager.return_value.process_source.return_value = SourceResult("Caption text", "creator_captions", caption_language="en")
        transcribe_youtube.run(job.pk, transcript.pk, [])
        transcript.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transcript.transcript_text, "Caption text")
        self.assertEqual(transcript.source_status, "ready")
        self.assertEqual(attempt.billing_state, "finalized")
        self.assertTrue(attempt.caption_delivery)
        self.assertFalse(UsageEvent.objects.exists())
        self.assertFalse(Summary.objects.exists())
        tagging.assert_not_called()
        with self.assertRaises(Ignore):
            transcribe_youtube.run(job.pk, transcript.pk, [])
        manager.return_value.process_source.assert_called_once()
        response = self.client.get(reverse("transcription:view_transcript", args=[transcript.pk]))
        self.assertContains(response, "Caption text")
        self.assertContains(response, "Creator-provided English captions")

    @patch("transcription.tasks.TaggingManager")
    @patch("transcription.tasks.TranscriptionManager")
    def test_selected_topics_tag_after_delivery_and_failure_preserves_text(self, manager, tagging):
        transcript, job, attempt = self.make_job()
        topic = Topic.objects.create(created_by=self.user, topic="Topic")
        manager.return_value.process_source.return_value = SourceResult("Saved captions", "automatic_captions")
        tagging.return_value.tag_transcript.side_effect = RuntimeError("tagging failure")
        with self.assertRaises(RuntimeError):
            transcribe_youtube.run(job.pk, transcript.pk, [topic.pk])
        transcript.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transcript.source_status, "ready")
        self.assertEqual(transcript.transcript_text, "Saved captions")
        self.assertEqual(attempt.billing_state, "finalized")
        tagging.assert_called_once()

    @patch("transcription.tasks.TranscriptionManager")
    def test_source_failure_is_visible_and_nonbillable(self, manager):
        transcript, job, attempt = self.make_job()
        manager.return_value.process_source.side_effect = SourceError("Only English audio is supported.")
        manager.return_value.retrieval_errors = ["Captions unavailable."]
        with self.assertRaises(SourceError):
            transcribe_youtube.run(job.pk, transcript.pk, [])
        transcript.refresh_from_db()
        job.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(transcript.source_status, "failed")
        self.assertEqual(job.error_message, "Only English audio is supported.")
        self.assertEqual(attempt.billing_state, "not_billable")

    def test_database_deduplication_constraint(self):
        self.make_job()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Transcript.objects.create(created_by=self.user, name="Duplicate", source_type="youtube", video_id=VIDEO)

    @patch("transcription.views.tag_saved_transcript")
    def test_initial_tagging_and_additional_tagging_cannot_overlap(self, task):
        transcript, job, attempt = self.make_job()
        transcript.source_status = "ready"
        transcript.save()
        job.processing_stage = "tagging"
        job.save()
        topic = Topic.objects.create(created_by=self.user, topic="Another topic")
        self.assertEqual(self.submit(topics=json.dumps([topic.topic])).status_code, 400)
        task.apply_async.assert_not_called()

    def test_no_usage_is_allowed_only_for_explicit_caption_delivery(self):
        transcript, job, attempt = self.make_job()
        record_transcript_delivery(attempt.pk, "text")
        from transcription.services.pricing import UsageEventLifecycleError
        with self.assertRaises(UsageEventLifecycleError):
            finalize_transcription_billing(attempt.pk)

    def test_delivery_does_not_finish_youtube_job_before_tagging_completes(self):
        from transcription.serializers import BackgroundJobSerializer
        transcript, job, attempt = self.make_job()
        record_transcript_delivery(attempt.pk, "Saved text", source_result=SourceResult("Saved text", "creator_captions"))
        job.processing_stage = "checking_captions"
        serializer = BackgroundJobSerializer()
        with patch.object(serializer, "_task", return_value=SimpleNamespace(status="STARTED")):
            self.assertEqual(serializer.get_status(job), "STARTED")
        job.processing_stage = "complete"
        self.assertEqual(serializer.get_status(job), "SUCCESS")

    @patch("transcription.views.transcribe_youtube")
    def test_broker_failure_is_explicitly_retryable(self, task):
        task.apply_async.side_effect = RuntimeError("Broker unavailable")
        self.submit()
        saved = Transcript.objects.get()
        self.assertEqual(saved.source_status, "failed")
        self.assertEqual(TranscriptionBillingAttempt.objects.get().billing_state, "not_billable")

    @patch("transcription.views.tag_saved_transcript")
    def test_saved_transcript_analysis_queues_tagging_and_duplicate_delivery_skips(self, task):
        transcript, original_job, _ = self.make_job()
        original_job.processing_stage = "complete"
        original_job.save()
        transcript.source_status = "ready"
        transcript.transcript_text = "Saved text"
        transcript.save()
        topic = Topic.objects.create(created_by=self.user, topic="New topic")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("transcription:view_transcript", args=[transcript.pk]),
                                        {"topics": json.dumps([topic.topic])})
        self.assertEqual(response.status_code, 302)
        job = BackgroundJob.objects.get(kind="tagging")
        task.apply_async.assert_called_once()
        with self.captureOnCommitCallbacks(execute=True):
            duplicate = self.client.post(reverse("transcription:view_transcript", args=[transcript.pk]),
                                         {"topics": json.dumps([topic.topic])})
        self.assertEqual(duplicate.status_code, 409)
        task.apply_async.assert_called_once()
        with patch("transcription.tasks.TaggingManager") as tagging:
            tag_saved_transcript.run(job.pk, transcript.pk, [topic.pk])
            with self.assertRaises(Ignore):
                tag_saved_transcript.run(job.pk, transcript.pk, [topic.pk])
            tagging.return_value.tag_transcript.assert_called_once()

    @override_settings(TRANSCRIPTION_MODEL="gpt-transcribe")
    @patch.dict(os.environ, {"MODEL_ENV": "test", "OPENAI_API_KEY": "test-key", "TRANSCRIPTION_MAX_CONCURRENT_CHUNKS": "1"})
    def test_audio_billing_and_non_english_rejection_use_real_chunk_lifecycle(self):
        from decimal import Decimal
        for fail_language in [False, True]:
            with self.subTest(non_english=fail_language):
                # Separate users/video IDs give independent real attempts.
                user = get_user_model().objects.create_user(username=f"audio-{fail_language}")
                transcript = Transcript.objects.create(created_by=user, name="Audio", source_type="youtube", source_url=URL, video_id=VIDEO)
                job = BackgroundJob.objects.create(created_by=user, kind="transcription", task_id=f"audio-{fail_language}", related_object_id=transcript.pk)
                attempt = TranscriptionBillingAttempt.objects.create(background_job=job, transcript=transcript)
                folders = []

                def retrieve(operation, url, folder=None):
                    if operation == "metadata":
                        return metadata(duration=20)
                    folders.append(folder)
                    path = Path(folder) / "audio.webm"
                    path.write_bytes(b"downloaded")
                    return {"path": str(path)}

                def manager_factory(*args, **kwargs):
                    manager = TranscriptionManager(*args, **kwargs)
                    def prepare():
                        manager.file_duration = 20
                        manager.chunk_length_sec = 10
                    manager._prepare_audio = prepare
                    def chunk(start_time=0, duration=10):
                        path = str(Path(manager.file_path).with_name(f"chunk-{start_time}.wav"))
                        with wave.open(path, "wb") as output:
                            output.setnchannels(1)
                            output.setsampwidth(2)
                            output.setframerate(16000)
                            output.writeframes(b"\0" * int(duration * 32000))
                        return path, 0.01
                    manager.read_audio_chunk = chunk
                    return manager

                responses = [SimpleNamespace(text="First English part", id=f"first-{fail_language}", languages=[{"code": "en"}]),
                    SimpleNamespace(text="Second part", id=f"second-{fail_language}", languages=[{"code": "es" if fail_language else "en"}])]
                with patch("transcription.transcription_utils.transcription_manager.YouTubeSource") as source, \
                     patch("transcription.tasks.TranscriptionManager", side_effect=manager_factory), \
                     patch.object(TranscriptionManager, "_transcribe_chunk_file", side_effect=responses):
                    source.return_value.retrieve.side_effect = retrieve
                    if fail_language:
                        with self.assertRaisesRegex(SourceError, "non-English"):
                            transcribe_youtube.run(job.pk, transcript.pk, [])
                    else:
                        transcribe_youtube.run(job.pk, transcript.pk, [])
                transcript.refresh_from_db()
                attempt.refresh_from_db()
                self.assertFalse(Path(folders[0]).exists())
                events = UsageEvent.objects.filter(transcription_attempt=attempt)
                self.assertEqual(events.count(), 2)
                if fail_language:
                    self.assertEqual(transcript.transcript_text, "")
                    self.assertEqual(attempt.billing_state, "not_billable")
                    self.assertFalse(events.exclude(billed_cost=Decimal("0")).exists())
                    self.assertFalse(events.filter(status="succeeded").exists())
                else:
                    self.assertEqual(transcript.provenance, "audio_transcription")
                    self.assertEqual(transcript.transcript_text, "First English part\nSecond part")
                    self.assertEqual(attempt.billing_state, "finalized")
                    self.assertFalse(events.exclude(status="succeeded").exists())
                    self.assertTrue(events.filter(billed_cost__gt=0).exists())
                self.assertFalse(Summary.objects.filter(transcript=transcript).exists())
