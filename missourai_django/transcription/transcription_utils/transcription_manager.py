# src/transcription_manager.py
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from typing import Optional

import openai
from openai import OpenAI

logger = logging.getLogger(__name__)


class TranscriptionMediaError(Exception):
    pass


def _elapsed_ms(start_time: float) -> int:
    return round((time.monotonic() - start_time) * 1000)


class TranscriptionManager:
    def __init__(
        self,
        api_key: str,
        file_path: str,
        max_file_size: int = 20,
        max_split_depth: int = 3,
        min_chunk_duration_sec: int = 15,
    ):
        init_started = time.monotonic()
        source_size = os.path.getsize(file_path) if os.path.exists(file_path) else "<missing>"
        logger.info(
            "transcription_timing event=manager_init_start file=%s source_size=%s",
            file_path,
            source_size,
        )

        client_started = time.monotonic()
        self.client = OpenAI(api_key=api_key)
        logger.info(
            "transcription_timing event=openai_client_init elapsed_ms=%s",
            _elapsed_ms(client_started),
        )

        self.max_file_size = max_file_size
        self.file_path = file_path
        self.max_split_depth = max_split_depth
        self.min_chunk_duration_sec = min_chunk_duration_sec
        self.issue_marker_template = (
            "[Transcription warning: audio from {start} to {end} "
            "could not be processed automatically.]"
        )
        self.normalized_audio_path: Optional[str] = None
        self.chunk_path: Optional[str] = None

        # Calculate chunk settings
        self.chunk_settings = {
            "channels": 1,
            "sample_rate": 16000,
            "bit_depth": 2,
        }
        self.chunk_length_sec = math.floor(
            (self.max_file_size * 1024 * 1024)
            / (
                self.chunk_settings["sample_rate"]
                * self.chunk_settings["bit_depth"]
                * self.chunk_settings["channels"]
            )
        )

        probe_started = time.monotonic()
        raw_probe_data = self._probe_media(
            self.file_path,
            read_error_message="Could not read the uploaded media file.",
            inspect_error_message="Could not inspect the uploaded media file.",
        )
        logger.info(
            "transcription_timing event=raw_probe elapsed_ms=%s",
            _elapsed_ms(probe_started),
        )
        self._ensure_audio_stream(raw_probe_data)

        try:
            normalize_started = time.monotonic()
            self._normalize_audio_source()
            normalized_size = (
                os.path.getsize(self.normalized_audio_path)
                if self.normalized_audio_path and os.path.exists(self.normalized_audio_path)
                else "<missing>"
            )
            logger.info(
                "transcription_timing event=normalize_source elapsed_ms=%s normalized_size=%s normalized_path=%s",
                _elapsed_ms(normalize_started),
                normalized_size,
                self.normalized_audio_path,
            )

            normalized_probe_started = time.monotonic()
            normalized_probe_data = self._probe_media(
                self.normalized_audio_path,
                read_error_message="Could not read the normalized audio track.",
                inspect_error_message="Could not inspect the normalized audio track.",
            )
            logger.info(
                "transcription_timing event=normalized_probe elapsed_ms=%s",
                _elapsed_ms(normalized_probe_started),
            )
            try:
                self.file_duration = float(normalized_probe_data["format"]["duration"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TranscriptionMediaError("Could not determine media duration.") from exc
        except Exception:
            logger.exception(
                "transcription_timing event=manager_init_failed elapsed_ms=%s",
                _elapsed_ms(init_started),
            )
            self._cleanup_normalized_audio()
            raise

        logger.info(
            "transcription_timing event=manager_init_complete elapsed_ms=%s file_duration_sec=%.2f chunk_length_sec=%s",
            _elapsed_ms(init_started),
            self.file_duration,
            self.chunk_length_sec,
        )

    def _probe_media(
        self,
        path: str,
        read_error_message: str,
        inspect_error_message: str,
    ) -> dict:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-show_entries", "format=duration",
                path,
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise TranscriptionMediaError(read_error_message)

        try:
            return json.loads(probe.stdout)
        except json.JSONDecodeError as exc:
            raise TranscriptionMediaError(inspect_error_message) from exc

    def _ensure_audio_stream(self, probe_data: dict):
        audio_streams = [
            stream
            for stream in probe_data.get("streams", [])
            if stream.get("codec_type") == "audio"
        ]
        if not audio_streams:
            raise TranscriptionMediaError(
                "The uploaded file does not contain an audio track."
            )

    def _normalize_audio_source(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
            self.normalized_audio_path = tmp_audio.name

        ffmpeg_started = time.monotonic()
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", self.file_path,
                "-map", "0:a:0",
                "-vn",
                "-af", "aresample=async=1:first_pts=0",
                "-ac", str(self.chunk_settings["channels"]),
                "-ar", str(self.chunk_settings["sample_rate"]),
                "-c:a", "pcm_s16le",
                "-f", "wav",
                self.normalized_audio_path,
            ],
            capture_output=True,
            text=True,
        )
        logger.info(
            "transcription_timing event=normalize_ffmpeg elapsed_ms=%s returncode=%s",
            _elapsed_ms(ffmpeg_started),
            result.returncode,
        )

        if result.returncode != 0:
            self._cleanup_normalized_audio()
            raise TranscriptionMediaError(
                "Could not normalize the uploaded audio track."
            )

    def read_audio_chunk(
        self,
        start_time: float = 0,
        duration: Optional[float] = None,
    ):
        duration = duration if duration is not None else self.chunk_length_sec

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_chunk:
            self.chunk_path = tmp_chunk.name

        chunk_started = time.monotonic()
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", self.normalized_audio_path,
                "-ac", str(self.chunk_settings["channels"]),
                "-ar", str(self.chunk_settings["sample_rate"]),
                "-c:a", "pcm_s16le",
                "-f", "wav",
                self.chunk_path,
            ],
            capture_output=True,
            text=True,
        )
        chunk_size = (
            os.path.getsize(self.chunk_path)
            if self.chunk_path and os.path.exists(self.chunk_path)
            else "<missing>"
        )
        logger.info(
            "transcription_timing event=extract_chunk start_time=%.2f duration=%.2f elapsed_ms=%s returncode=%s chunk_size=%s",
            start_time,
            duration,
            _elapsed_ms(chunk_started),
            result.returncode,
            chunk_size,
        )

        if result.returncode != 0:
            raise TranscriptionMediaError("Could not extract audio from the uploaded file.")

    def _transcribe_current_chunk_file(self) -> str:
        if os.getenv("MODEL_ENV") == "dev":
            logger.info("transcription_timing event=api_call_bypass model_env=dev")
            return "Short transcript text resembling actual API output."

        api_started = time.monotonic()
        with open(self.chunk_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
            )
        logger.info(
            "transcription_timing event=openai_transcription elapsed_ms=%s chunk_path=%s",
            _elapsed_ms(api_started),
            self.chunk_path,
        )
        return transcript.text

    def _should_split_on_error(self, exc: Exception) -> bool:
        if isinstance(exc, TranscriptionMediaError):
            return True

        if isinstance(exc, openai.BadRequestError):
            if exc.code in {"invalid_value", "audio_too_short"}:
                return True

            message = str(exc).lower()
            return "corrupted or unsupported" in message

        return False

    def _format_seconds(self, seconds: float) -> str:
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _issue_marker(self, start_time: float, duration: float) -> str:
        return self.issue_marker_template.format(
            start=self._format_seconds(start_time),
            end=self._format_seconds(start_time + duration),
        )

    def _join_transcript_parts(self, parts: list[str]) -> str:
        return "\n".join(part for part in parts if part).strip()

    def _split_or_mark(
        self,
        start_time: float,
        duration: float,
        split_depth: int,
        reason: Exception,
    ) -> str:
        if split_depth >= self.max_split_depth or duration <= self.min_chunk_duration_sec:
            logger.warning(
                "transcription_timing event=fallback_limit start_time=%.2f duration=%.2f reason=%s",
                start_time,
                duration,
                reason,
            )
            return self._issue_marker(start_time, duration)

        half = duration / 2
        logger.warning(
            "transcription_timing event=split_failed_segment start_time=%.2f duration=%.2f split_depth=%s max_split_depth=%s",
            start_time,
            duration,
            split_depth + 1,
            self.max_split_depth,
        )

        left = self._transcribe_range_with_fallback(
            start_time=start_time,
            duration=half,
            split_depth=split_depth + 1,
        )
        right = self._transcribe_range_with_fallback(
            start_time=start_time + half,
            duration=duration - half,
            split_depth=split_depth + 1,
        )
        return self._join_transcript_parts([left, right])

    def _transcribe_range_with_fallback(
        self,
        start_time: float,
        duration: float,
        split_depth: int = 0,
    ) -> str:
        range_started = time.monotonic()
        try:
            try:
                self.read_audio_chunk(start_time=start_time, duration=duration)
                logger.info(
                    "transcription_timing event=chunk_ready start_time=%.2f duration=%.2f",
                    start_time,
                    duration,
                )
                return self._transcribe_current_chunk_file()
            finally:
                self._cleanup_chunk()

        except openai.BadRequestError as exc:
            if exc.code == "audio_too_short":
                logger.info(
                    "transcription_timing event=skip_short_audio start_time=%.2f duration=%.2f elapsed_ms=%s",
                    start_time,
                    duration,
                    _elapsed_ms(range_started),
                )
                return ""

            if not self._should_split_on_error(exc):
                raise

            return self._split_or_mark(
                start_time=start_time,
                duration=duration,
                split_depth=split_depth,
                reason=exc,
            )

        except TranscriptionMediaError as exc:
            return self._split_or_mark(
                start_time=start_time,
                duration=duration,
                split_depth=split_depth,
                reason=exc,
            )
        finally:
            logger.info(
                "transcription_timing event=transcribe_range_complete start_time=%.2f duration=%.2f split_depth=%s elapsed_ms=%s",
                start_time,
                duration,
                split_depth,
                _elapsed_ms(range_started),
            )

    def _cleanup_chunk(self):
        if not self.chunk_path:
            return

        try:
            os.remove(self.chunk_path)
        except FileNotFoundError:
            pass
        finally:
            self.chunk_path = None

    def _cleanup_normalized_audio(self):
        if not self.normalized_audio_path:
            return

        try:
            os.remove(self.normalized_audio_path)
        except FileNotFoundError:
            pass
        finally:
            self.normalized_audio_path = None

    def create_transcript(self) -> str:
        transcript_started = time.monotonic()
        pieces: list[str] = []
        start_time = 0.0
        chunk_index = 1
        target_chunks = math.ceil(self.file_duration / self.chunk_length_sec)

        try:
            while start_time < self.file_duration:
                duration = min(self.chunk_length_sec, self.file_duration - start_time)
                chunk_started = time.monotonic()
                logger.info(
                    "transcription_timing event=process_chunk_start chunk_index=%s target_chunks=%s start_time=%.2f duration=%.2f",
                    chunk_index,
                    target_chunks,
                    start_time,
                    duration,
                )

                piece = self._transcribe_range_with_fallback(
                    start_time=start_time,
                    duration=duration,
                    split_depth=0,
                )
                pieces.append(piece)
                logger.info(
                    "transcription_timing event=process_chunk_complete chunk_index=%s target_chunks=%s elapsed_ms=%s transcript_chars=%s",
                    chunk_index,
                    target_chunks,
                    _elapsed_ms(chunk_started),
                    len(piece),
                )

                start_time += duration
                chunk_index += 1

            return self._join_transcript_parts(pieces)
        finally:
            logger.info(
                "transcription_timing event=create_transcript_complete elapsed_ms=%s chunks_completed=%s target_chunks=%s",
                _elapsed_ms(transcript_started),
                chunk_index - 1,
                target_chunks,
            )
            self._cleanup_chunk()
            self._cleanup_normalized_audio()
