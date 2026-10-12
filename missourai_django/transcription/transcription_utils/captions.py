"""JSON3 captions retain enough timing information to resolve rolling updates."""
import html
import math
import re
from urllib.parse import parse_qs, urlsplit

from .sources import SourceError


def english_tracks(info):
    for kind, provenance in (("subtitles", "creator_captions"), ("automatic_captions", "automatic_captions")):
        # Prefer original identifiers; don't emit the same format URL twice.
        seen = set()
        tracks = info.get(kind) or {}
        for language in sorted(tracks, key=lambda code: (not code.endswith("-orig"), code)):
            original = language.removesuffix("-orig").lower()
            if not re.fullmatch(r"en(?:-[a-z]{2})?", original):
                continue
            for track in tracks[language]:
                query = parse_qs(urlsplit(track.get("url", "")).query, keep_blank_values=True)
                actual = query.get("lang", [original])[0].lower()
                if ("tlang" in query or len(query.get("lang", [original])) != 1 or not re.fullmatch(r"en(?:-[a-z]{2})?", actual)
                        or track.get("ext") != "json3" or track.get("url") in seen):
                    continue
                seen.add(track["url"])
                yield provenance, original, track["url"]


def normalize_json3(data, duration, gap_seconds=300):
    cues = []
    for order, event in enumerate(data.get("events", [])):
        if not event.get("segs"):
            continue  # Window/style events contain no spoken text.
        try:
            start = float(event["tStartMs"]) / 1000
            length = float(event.get("dDurationMs", 0)) / 1000
            text = "".join(segment.get("utf8", "") for segment in event["segs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError("English captions contain invalid timing or text.") from exc
        if not math.isfinite(start) or not math.isfinite(length) or start < 0 or length < 0:
            raise SourceError("English captions contain invalid timing.")
        if start > duration + 5:
            raise SourceError("English captions extend beyond the video duration.")
        text = re.sub(r"<[^>]*>", "", html.unescape(text))
        text = " ".join(text.split())
        if text:
            cues.append((start, min(duration, start + length), order, text, event.get("wWinId"), bool(event.get("aAppend"))))
    if not cues:
        raise SourceError("English captions contain no readable text.")
    cues.sort(key=lambda cue: (cue[0], cue[2]))
    pieces = []
    previous = None
    rolling_start = 0
    covered_end = 0
    warnings = []
    if cues[0][0] > gap_seconds:
        warnings.append(f"Captions begin more than {gap_seconds / 60:g} minutes into the video.")
    for cue in cues:
        start, end, _, text, window, append = cue
        if start - covered_end > gap_seconds and previous is not None:
            warnings.append(f"Captions contain a gap exceeding {gap_seconds / 60:g} minutes; this may be a recess.")
        # Append events contain NEW text. Overlap removal applies only to
        # rolling replacement cues in the same window with overlapping times.
        words = text.split()
        if previous and not append and start == previous[0] and window == previous[4]:
            # A replacement with the same start/window revises that cue; keep
            # its latest wording rather than retaining recognizer corrections.
            del pieces[rolling_start:]
        else:
            rolling_start = len(pieces)
        if (previous and not append and window is not None and start != previous[0]
                and start < previous[1] and window == previous[4]):
            prior_words = previous[3].split()
            for size in range(min(len(prior_words), len(words)), 0, -1):
                if (prior_words[-size:] == words[:size]
                        and len(words) > size and (size >= 2 or size == len(prior_words))):
                    words = words[size:]
                    break
        if words:
            pieces.append(" ".join(words))
        covered_end = max(covered_end, end)
        previous = cue
    if duration - covered_end > gap_seconds:
        warnings.append(f"Captions end more than {gap_seconds / 60:g} minutes before the video finishes.")
    return " ".join(pieces), list(dict.fromkeys(warnings))
