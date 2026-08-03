# src/transcription_manager.py
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import openai
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from openai import OpenAI

from transcription.models import TranscriptionChunkMetric, TranscriptionJobMetric

logger = logging.getLogger(__name__)

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
        max_concurrent_chunks: int = 2,
        job_metric: Optional[TranscriptionJobMetric] = None,
        model_name: Optional[str] = None,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name or settings.TRANSCRIPTION_MODEL
        self.max_file_size = max_file_size
        self.file_path = file_path
        self.max_split_depth = max_split_depth
        self.min_chunk_duration_sec = min_chunk_duration_sec
        self.max_concurrent_chunks = max(1, max_concurrent_chunks)
        self.job_metric = job_metric
        self.issue_marker_template = (
            "[Transcription warning: audio from {start} to {end} "
            "could not be processed automatically.]"
        )
        self.normalized_audio_path: Optional[str] = None
        self.file_duration: Optional[float] = None

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
        raw_file_duration = self._duration_from_probe(raw_probe_data)

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
            self._update_job_metric(
                audio_duration_sec=raw_file_duration,
                normalized_duration_sec=self.file_duration,
                max_concurrent_chunks=self.max_concurrent_chunks,
                model_name=self.model_name,
            )
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

    def _duration_from_probe(self, probe_data: dict) -> Optional[float]:
        try:
            return float(probe_data["format"]["duration"])
        except (KeyError, TypeError, ValueError):
            return None

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
    ) -> tuple[str, float]:
        duration = duration if duration is not None else self.chunk_length_sec

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_chunk:
            chunk_path = tmp_chunk.name

        started_at = time.perf_counter()
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
                chunk_path,
            ],
            capture_output=True,
            text=True,
        )
        ffmpeg_duration_sec = time.perf_counter() - started_at

        if result.returncode != 0:
            self._cleanup_chunk(chunk_path)
            raise TranscriptionMediaError("Could not extract audio from the uploaded file.")

        return chunk_path, ffmpeg_duration_sec

    def _transcribe_chunk_file(self, chunk_path: str) -> str:
        if os.getenv("MODEL_ENV") == "dev":
            logger.info("MODEL_ENV is DEV.  Bypassing external API calls.")
            return "Short transcript text resembling actual API output."

        with open(chunk_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model=self.model_name,
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
        chunk_index: int,
        reason: Exception,
    ) -> str:
        if split_depth >= self.max_split_depth or duration <= self.min_chunk_duration_sec:
            logger.warning(
                "Reached transcription fallback limit at %.2fs for %.2fs: %s",
                start_time,
                duration,
                reason,
            )
            return self._issue_marker(start_time, duration)

        half = duration / 2
        logger.warning(
            "Splitting failed transcription segment at %.2fs for %.2fs (depth %s/%s)",
            start_time,
            duration,
            split_depth + 1,
            self.max_split_depth,
        )

        left = self._transcribe_range_with_fallback(
            start_time=start_time,
            duration=half,
            chunk_index=chunk_index,
            split_depth=split_depth + 1,
        )
        right = self._transcribe_range_with_fallback(
            start_time=start_time + half,
            duration=duration - half,
            chunk_index=chunk_index,
            split_depth=split_depth + 1,
        )
        return self._join_transcript_parts([left, right])

    def _transcribe_range_with_fallback(
        self,
        start_time: float,
        duration: float,
        chunk_index: int,
        split_depth: int = 0,
    ) -> str:
        chunk_path = None
        chunk_metric = self._create_chunk_metric(
            chunk_index=chunk_index,
            start_time=start_time,
            duration=duration,
            split_depth=split_depth,
        )
        total_started_at = time.perf_counter()
        ffmpeg_duration_sec = None
        openai_duration_sec = None
        chunk_file_size_bytes = None
        try:
            try:
                chunk_path, ffmpeg_duration_sec = self.read_audio_chunk(
                    start_time=start_time,
                    duration=duration,
                )
                chunk_file_size_bytes = self._file_size(chunk_path)
                openai_started_at = time.perf_counter()
                transcript = self._transcribe_chunk_file(chunk_path)
                openai_duration_sec = time.perf_counter() - openai_started_at
                self._finish_chunk_metric(
                    chunk_metric,
                    status=TranscriptionChunkMetric.Status.SUCCESS,
                    total_duration_sec=time.perf_counter() - total_started_at,
                    chunk_file_size_bytes=chunk_file_size_bytes,
                    ffmpeg_duration_sec=ffmpeg_duration_sec,
                    openai_duration_sec=openai_duration_sec,
                )
                return transcript
            finally:
                self._cleanup_chunk(chunk_path)

        except openai.BadRequestError as exc:
            if exc.code == "audio_too_short":
                logger.info(
                    f"Skipping short audio segment at {start_time:.2f}s for {duration:.2f}s"
                )
                self._finish_chunk_metric(
                    chunk_metric,
                    status=TranscriptionChunkMetric.Status.SKIPPED,
                    total_duration_sec=time.perf_counter() - total_started_at,
                    chunk_file_size_bytes=chunk_file_size_bytes,
                    ffmpeg_duration_sec=ffmpeg_duration_sec,
                    openai_duration_sec=openai_duration_sec,
                    error=exc,
                )
                return ""

            if not self._should_split_on_error(exc):
                self._finish_chunk_metric(
                    chunk_metric,
                    status=TranscriptionChunkMetric.Status.FAILED,
                    total_duration_sec=time.perf_counter() - total_started_at,
                    chunk_file_size_bytes=chunk_file_size_bytes,
                    ffmpeg_duration_sec=ffmpeg_duration_sec,
                    openai_duration_sec=openai_duration_sec,
                    error=exc,
                )
                raise

            self._finish_chunk_metric(
                chunk_metric,
                status=TranscriptionChunkMetric.Status.FAILED,
                total_duration_sec=time.perf_counter() - total_started_at,
                chunk_file_size_bytes=chunk_file_size_bytes,
                ffmpeg_duration_sec=ffmpeg_duration_sec,
                openai_duration_sec=openai_duration_sec,
                error=exc,
            )
            return self._split_or_mark(
                start_time=start_time,
                duration=duration,
                split_depth=split_depth,
                chunk_index=chunk_index,
                reason=exc,
            )

        except TranscriptionMediaError as exc:
            self._finish_chunk_metric(
                chunk_metric,
                status=TranscriptionChunkMetric.Status.FAILED,
                total_duration_sec=time.perf_counter() - total_started_at,
                chunk_file_size_bytes=chunk_file_size_bytes,
                ffmpeg_duration_sec=ffmpeg_duration_sec,
                openai_duration_sec=openai_duration_sec,
                error=exc,
            )
            return self._split_or_mark(
                start_time=start_time,
                duration=duration,
                split_depth=split_depth,
                chunk_index=chunk_index,
                reason=exc,
            )
    def _cleanup_chunk(self, chunk_path: Optional[str]):
        if not chunk_path:
            return

        try:
            os.remove(chunk_path)
        except FileNotFoundError:
            pass

    def _file_size(self, path: Optional[str]) -> Optional[int]:
        if not path:
            return None

        try:
            return os.path.getsize(path)
        except OSError:
            return None

    def _update_job_metric(self, **fields):
        if not self.job_metric:
            return

        for field, value in fields.items():
            setattr(self.job_metric, field, value)
        self.job_metric.save(update_fields=list(fields))

    def _create_chunk_metric(
        self,
        chunk_index: int,
        start_time: float,
        duration: float,
        split_depth: int,
    ) -> Optional[TranscriptionChunkMetric]:
        if not self.job_metric:
            return None

        return TranscriptionChunkMetric.objects.create(
            job_metric=self.job_metric,
            chunk_index=chunk_index,
            start_time_sec=start_time,
            duration_sec=duration,
            split_depth=split_depth,
        )

    def _finish_chunk_metric(
        self,
        chunk_metric: Optional[TranscriptionChunkMetric],
        status: str,
        total_duration_sec: float,
        chunk_file_size_bytes: Optional[int] = None,
        ffmpeg_duration_sec: Optional[float] = None,
        openai_duration_sec: Optional[float] = None,
        error: Optional[Exception] = None,
    ):
        if not chunk_metric:
            return

        chunk_metric.status = status
        chunk_metric.finished_at = timezone.now()
        chunk_metric.total_duration_sec = total_duration_sec
        chunk_metric.chunk_file_size_bytes = chunk_file_size_bytes
        chunk_metric.ffmpeg_duration_sec = ffmpeg_duration_sec
        chunk_metric.openai_duration_sec = openai_duration_sec
        if error:
            chunk_metric.error_type = error.__class__.__name__
            chunk_metric.error_message = str(error)
        chunk_metric.save(
            update_fields=[
                "status",
                "finished_at",
                "total_duration_sec",
                "chunk_file_size_bytes",
                "ffmpeg_duration_sec",
                "openai_duration_sec",
                "error_type",
                "error_message",
            ]
        )

    def _cleanup_normalized_audio(self):
        if not self.normalized_audio_path:
            return

        try:
            os.remove(self.normalized_audio_path)
        except FileNotFoundError:
            pass
        finally:
            self.normalized_audio_path = None

    def _build_chunk_ranges(self) -> list[tuple[int, float, float]]:
        chunks = []
        start_time = 0.0
        chunk_index = 1

        while start_time < self.file_duration:
            duration = min(self.chunk_length_sec, self.file_duration - start_time)
            chunks.append((chunk_index, start_time, duration))
            start_time += duration
            chunk_index += 1

        return chunks

    def _transcribe_chunk_range(
        self,
        chunk_index: int,
        target_chunks: int,
        start_time: float,
        duration: float,
    ) -> str:
        close_old_connections()
        try:
            print(f"Processing chunk {chunk_index} of {target_chunks}")
            return self._transcribe_range_with_fallback(
                start_time=start_time,
                duration=duration,
                chunk_index=chunk_index,
                split_depth=0,
            )
        finally:
            close_old_connections()

    def create_transcript(self) -> str:
        chunks = self._build_chunk_ranges()
        target_chunks = len(chunks)
        self._update_job_metric(chunk_count=target_chunks)

        try:
            if self.max_concurrent_chunks == 1 or target_chunks <= 1:
                pieces = []
                for chunk_index, start_time, duration in chunks:
                    print(f"Processing chunk {chunk_index} of {target_chunks}")
                    pieces.append(
                        self._transcribe_range_with_fallback(
                            start_time=start_time,
                            duration=duration,
                            chunk_index=chunk_index,
                            split_depth=0,
                        )
                    )
                return self._join_transcript_parts(pieces)

            pieces_by_index = {}
            max_workers = min(self.max_concurrent_chunks, target_chunks)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._transcribe_chunk_range,
                        chunk_index,
                        target_chunks,
                        start_time,
                        duration,
                    ): chunk_index
                    for chunk_index, start_time, duration in chunks
                }

                try:
                    for future in as_completed(futures):
                        chunk_index = futures[future]
                        pieces_by_index[chunk_index] = future.result()
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise

            return self._join_transcript_parts([
                pieces_by_index[index]
                for index in sorted(pieces_by_index)
            ])
        finally:
            self._cleanup_normalized_audio()
