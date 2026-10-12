"""Bounded, credential-free YouTube retrieval behind the manager."""
import json
from pathlib import Path
import subprocess
import sys
import time

from django.conf import settings

from .sources import SourceError


class YouTubeSource:
    def retrieve(self, operation, source, directory=None):
        command = [sys.executable, str(Path(__file__).with_name("youtube_worker.py")), operation, source,
                   "--max-duration", str(settings.YOUTUBE_MAX_DURATION_SECONDS),
                   "--socket-timeout", str(settings.YOUTUBE_SOCKET_TIMEOUT_SECONDS),
                   "--max-bytes", str(settings.YOUTUBE_MAX_DOWNLOAD_BYTES)]
        if directory:
            command += ["--directory", str(directory)]
        timeout = (settings.YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS if operation == "audio"
                   else settings.YOUTUBE_RETRIEVAL_TIMEOUT_SECONDS)
        # No whole-job retry. These attempts happen strictly before STT calls.
        for attempt in range(settings.YOUTUBE_RETRIEVAL_ATTEMPTS):
            try:
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
                if result.returncode == 0:
                    return json.loads(result.stdout)
                detail = result.stderr.lower()
                if "duration limit" in detail:
                    raise SourceError(f"The video exceeds the {settings.YOUTUBE_MAX_DURATION_SECONDS / 3600:g}-hour duration limit.")
                if "completed videos" in detail:
                    raise SourceError("Active, upcoming, or unavailable livestreams are not supported.")
                if "private" in detail or "unavailable" in detail or "age-restricted" in detail:
                    raise SourceError("This video is inaccessible or restricted. Please use a public video.")
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                pass
            if attempt + 1 < settings.YOUTUBE_RETRIEVAL_ATTEMPTS:
                time.sleep(min(attempt + 1, 3))
        messages = {"metadata": "Could not retrieve this public video's metadata.",
                    "caption": "English captions could not be retrieved.",
                    "audio": "The video audio could not be downloaded."}
        raise SourceError(messages[operation])
