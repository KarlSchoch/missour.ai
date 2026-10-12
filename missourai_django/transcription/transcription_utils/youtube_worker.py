"""Isolated retrieval process: parent enforces a hard wall-clock timeout.

No Django imports, cookies, credentials, plugins, or generic URL extractor.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class CaptionRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        validate_caption_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def validate_caption_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or not (host == "youtube.com" or host.endswith(".youtube.com"))):
        raise ValueError("Unsupported caption endpoint.")
    for address in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("Unsupported caption endpoint address.")


def eligible(info, limit):
    from sources import validate_video_metadata
    return validate_video_metadata(info, limit)


def run(args):
    if args.operation == "caption":
        validate_caption_url(args.source)
        with build_opener(CaptionRedirects()).open(Request(args.source), timeout=args.socket_timeout) as response:
            content = response.read(64 * 1024 * 1024 + 1)
        if len(content) > 64 * 1024 * 1024:
            raise ValueError("Caption data exceeds the supported size.")
        return json.loads(content)

    os.environ["YTDLP_NO_PLUGINS"] = "1"
    from yt_dlp import YoutubeDL

    def video_filter(info, *, incomplete=False):
        if not incomplete:
            eligible(info, args.max_duration)
        return None

    def download_progress(progress):
        if progress.get("downloaded_bytes", 0) > args.max_bytes:
            raise ValueError("Audio download exceeds the configured size limit.")
    # Only canonical URLs supplied by the manager reach the extractor.
    import re
    if not re.fullmatch(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", args.source):
        raise ValueError("Unsupported YouTube URL.")
    options = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "socket_timeout": args.socket_timeout, "retries": 1,
        "fragment_retries": 1, "extractor_retries": 1,
        "extractor_args": {"youtube": {"skip": ["translated_subs"]}},
        "allowed_extractors": ["youtube"],
        "cachedir": False, "js_runtimes": {"deno": {}},
        "format": "bestaudio", "skip_download": args.operation == "metadata",
        "ignore_no_formats_error": args.operation == "metadata",
        "match_filter": video_filter,
    }
    if args.operation == "audio":
        options["outtmpl"] = str(Path(args.directory) / "audio.%(ext)s")
        options["progress_hooks"] = [download_progress]
        options["max_filesize"] = args.max_bytes
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(args.source, download=args.operation == "audio")
        eligible(info, args.max_duration)
        if args.operation == "audio":
            path = Path(downloader.prepare_filename(info))
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError("The audio download did not produce a usable file.")
            return {"path": str(path)}
        return {key: info.get(key) for key in (
            "id", "title", "duration", "live_status", "availability", "language",
            "subtitles", "automatic_captions",
        )}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["metadata", "caption", "audio"])
    parser.add_argument("source")
    parser.add_argument("--directory", default="")
    parser.add_argument("--socket-timeout", type=int, default=20)
    parser.add_argument("--max-duration", type=int, default=28800)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 ** 3)
    try:
        result = run(parser.parse_args())
        sys.stdout.write(json.dumps(result))
    except Exception as exc:
        # The parent records sanitized failures; signed URLs never enter the DB/UI.
        sys.stderr.write(str(exc))
        sys.exit(1)
