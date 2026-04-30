# src/transcription_manager.py
import json
import math
import os
import subprocess
import tempfile
from typing import Optional

import openai
from openai import OpenAI


class TranscriptionMediaError(Exception):
    pass


class TranscriptionManager:
    def __init__(
        self,
        api_key: str,
        file_path: str,
        max_file_size: int = 20,
        max_split_depth: int = 3,
        min_chunk_duration_sec: int = 15,
    ):
        self.client = OpenAI(api_key=api_key)
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

        raw_probe_data = self._probe_media(
            self.file_path,
            read_error_message="Could not read the uploaded media file.",
            inspect_error_message="Could not inspect the uploaded media file.",
        )
        self._ensure_audio_stream(raw_probe_data)

        try:
            self._normalize_audio_source()

            normalized_probe_data = self._probe_media(
                self.normalized_audio_path,
                read_error_message="Could not read the normalized audio track.",
                inspect_error_message="Could not inspect the normalized audio track.",
            )
            try:
                self.file_duration = float(normalized_probe_data["format"]["duration"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TranscriptionMediaError("Could not determine media duration.") from exc
        except Exception:
            self._cleanup_normalized_audio()
            raise

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

        if result.returncode != 0:
            raise TranscriptionMediaError("Could not extract audio from the uploaded file.")

    def _transcribe_current_chunk_file(self) -> str:
        if os.getenv("MODEL_ENV") == "dev":
            print("MODEL_ENV is DEV. Bypassing external API calls")
            return "Short transcript text resembling actual API output."

        with open(self.chunk_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
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
            print(
                f"Reached fallback limit at {start_time:.2f}s for {duration:.2f}s: {reason}"
            )
            return self._issue_marker(start_time, duration)

        half = duration / 2
        print(
            f"Splitting failed segment at {start_time:.2f}s for {duration:.2f}s "
            f"(depth {split_depth + 1}/{self.max_split_depth})"
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
        try:
            try:
                self.read_audio_chunk(start_time=start_time, duration=duration)
                print(
                    f"Prepared chunk start={start_time:.2f}s duration={duration:.2f}s"
                )
                return self._transcribe_current_chunk_file()
            finally:
                self._cleanup_chunk()

        except openai.BadRequestError as exc:
            if exc.code == "audio_too_short":
                print(
                    f"Skipping short audio segment at {start_time:.2f}s for {duration:.2f}s"
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
        pieces: list[str] = []
        start_time = 0.0
        chunk_index = 1
        target_chunks = math.ceil(self.file_duration / self.chunk_length_sec)

        try:
            while start_time < self.file_duration:
                duration = min(self.chunk_length_sec, self.file_duration - start_time)
                print(f"Processing chunk {chunk_index} of {target_chunks}")

                piece = self._transcribe_range_with_fallback(
                    start_time=start_time,
                    duration=duration,
                    split_depth=0,
                )
                pieces.append(piece)

                start_time += duration
                chunk_index += 1

            return self._join_transcript_parts(pieces)
        finally:
            self._cleanup_chunk()
            self._cleanup_normalized_audio()
