"""Source contracts shared by forms, the manager, and background processing."""
from dataclasses import dataclass, field
import re
import math
from urllib.parse import parse_qs, urlsplit


class SourceError(ValueError):
    """A source failure safe to show to the user."""


def validate_video_metadata(info, limit):
    duration = info.get("duration")
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration <= 0):
        raise SourceError("The video duration is unavailable.")
    if duration > limit:
        raise SourceError(f"The video exceeds the duration limit of {limit / 3600:g} hours.")
    if info.get("live_status") not in {"not_live", "was_live"}:
        raise SourceError("Only completed videos and available livestream archives are supported.")
    if info.get("availability") not in {"public", None}:
        raise SourceError("Only publicly accessible videos are supported.")
    if info.get("age_limit", 0) > 0:
        raise SourceError("Age-restricted videos are not supported.")
    return duration


def youtube_source(value):
    try:
        url = urlsplit(value.strip())
        if url.scheme not in {"http", "https"} or url.username or url.password:
            raise ValueError
        if url.port is not None or url.fragment:
            raise ValueError
        host = (url.hostname or "").lower()
        query = parse_qs(url.query, keep_blank_values=True)
        if "list" in query:
            raise SourceError("Please submit an individual video without a playlist parameter.")
        if host == "youtu.be":
            video_id = url.path.lstrip("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if url.path == "/watch" and len(query.get("v", [])) == 1:
                video_id = query["v"][0]
            elif re.fullmatch(r"/(shorts|embed|live)/[A-Za-z0-9_-]{11}", url.path):
                video_id = url.path.rsplit("/", 1)[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
    except (ValueError, AttributeError) as exc:
        if isinstance(exc, SourceError):
            raise
        raise SourceError("Enter a supported youtube.com or youtu.be video URL.") from exc
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


@dataclass
class SourceResult:
    text: str
    provenance: str
    title: str = ""
    duration: float | None = None
    caption_language: str = ""
    warnings: list = field(default_factory=list)
    retrieval_errors: list = field(default_factory=list)


def validate_english_response(response):
    """Validate detected input languages, never an imposed output-language hint."""
    def get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    languages = get(response, "languages")
    if languages is not None:
        codes = [get(language, "code", "") for language in languages]
    else:
        codes = [get(response, "language", "")]
    codes = [str(code).lower().replace("_", "-") for code in codes if code]
    if not codes:
        raise SourceError("The audio language could not be verified as English. Please use an English recording.")
    if any(code not in {"en", "eng", "english"} and not code.startswith("en-") for code in codes):
        raise SourceError("This video contains non-English speech. Only English audio is supported.")
