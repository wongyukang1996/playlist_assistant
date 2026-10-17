"""Turn YouTube video URLs into track dicts compatible with app.py."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtu.be",
}


class VideoImportError(Exception):
    pass


def extract_video_id(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _HOSTS:
        return None

    if host.endswith("youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
    else:
        parts = [p for p in parsed.path.split("/") if p]
        if parsed.path.rstrip("/") == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live"):
            candidate = parts[1]
        else:
            return None
    return candidate if _ID_RE.match(candidate) else None


def format_duration(seconds: Any) -> str | None:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return None
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def fetch_video_track(client, video_id: str, index: int, raw: str) -> dict[str, Any]:
    """Build a pre-confirmed track dict. Raises VideoImportError on failure."""
    try:
        data = client.get_song(video_id)
    except Exception as exc:
        raise VideoImportError(f"Could not load video: {exc}") from exc

    details = (data or {}).get("videoDetails") or {}
    title = (details.get("title") or "").strip()
    if not title:
        raise VideoImportError("Video is unavailable (private, deleted or region-blocked).")
    author = (details.get("author") or "").strip().removesuffix(" - Topic") or "Unknown"

    return {
        "id": f"{index}:{title}:{author}",
        "line_number": index,
        "original_title": title,
        "original_singer": author,
        "raw": raw,
        "candidates": [
            {
                "video_id": video_id,
                "title": title,
                "artists": author,
                "album": None,
                "duration": format_duration(details.get("lengthSeconds")),
                "url": f"https://music.youtube.com/watch?v={video_id}",
            }
        ],
        "selected_video_id": video_id,
        "confirmed": True,
        "included": True,
        "search_error": None,
        "searched": True,
    }