"""Live YouTube Music search and candidate formatting."""

from __future__ import annotations

from typing import Any, Callable

MAX_CANDIDATES = 5
WATCH_URL = "https://music.youtube.com/watch?v={video_id}"


class SearchError(Exception):
    """Raised when a live YouTube Music search cannot be completed."""


def youtube_music_url(video_id: str | None) -> str | None:
    if not video_id:
        return None
    return WATCH_URL.format(video_id=video_id)


def _artist_names(item: dict[str, Any]) -> str | None:
    artists = item.get("artists")
    if not artists:
        return None
    names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name")
            if name:
                names.append(str(name))
        elif artist:
            names.append(str(artist))
    return ", ".join(names) if names else None


def _album_name(item: dict[str, Any]) -> str | None:
    album = item.get("album")
    if album is None:
        return None
    if isinstance(album, dict):
        name = album.get("name")
        return str(name) if name else None
    text = str(album).strip()
    return text or None


def format_candidate(item: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only fields that are actually present. Never invent values."""
    if not isinstance(item, dict):
        return None

    video_id = item.get("videoId")
    if not video_id:
        return None

    video_id = str(video_id)
    title = item.get("title")
    duration = item.get("duration")
    result_type = item.get("resultType")

    return {
        "title": str(title) if title else None,
        "artists": _artist_names(item),
        "album": _album_name(item),
        "duration": str(duration) if duration else None,
        "video_id": video_id,
        "url": youtube_music_url(video_id),
        "result_type": str(result_type) if result_type else None,
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        video_id = candidate.get("video_id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        unique.append(candidate)
    return unique


def _search_filter(client: Any, query: str, search_filter: str | None, limit: int) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"query": query, "limit": limit}
    if search_filter:
        kwargs["filter"] = search_filter
    results = client.search(**kwargs)
    if results is None:
        return []
    if not isinstance(results, list):
        raise SearchError("Unexpected search response from YouTube Music.")
    return results


def search_candidates(
    client: Any,
    title: str,
    singer: str,
    *,
    max_results: int = MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """Search YouTube Music using both song title and singer.

    Results come from live ``ytmusicapi`` queries. Empty lists are valid.
    """
    query = f"{title} {singer}".strip()
    if not query:
        return []

    try:
        raw_items = _search_filter(client, query, "songs", max_results)
        formatted = [c for item in raw_items if (c := format_candidate(item))]
        formatted = _dedupe_candidates(formatted)

        if len(formatted) < max_results:
            extra = _search_filter(client, query, None, max_results)
            for item in extra:
                candidate = format_candidate(item)
                if candidate:
                    formatted.append(candidate)
            formatted = _dedupe_candidates(formatted)
    except SearchError:
        raise
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "429" in message or "rate" in lowered:
            raise SearchError(
                "YouTube Music rate-limited or rejected the request. Wait a moment and search again."
            ) from exc
        if any(token in lowered for token in ("connection", "timeout", "timed out", "network")):
            raise SearchError(
                "Could not reach YouTube Music. Check your internet connection and try again."
            ) from exc
        raise SearchError(f"YouTube Music search failed: {message}") from exc

    return formatted[:max_results]


def search_many(
    client: Any,
    tracks: list[dict[str, Any]],
    *,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Search each track in order. Failures are stored on the track, not raised."""
    total = len(tracks)
    updated: list[dict[str, Any]] = []
    for index, track in enumerate(tracks, start=1):
        current = dict(track)
        if on_progress:
            on_progress(index, total, current)
        try:
            current["candidates"] = search_candidates(
                client,
                current["original_title"],
                current["original_singer"],
            )
            current["search_error"] = None
        except SearchError as exc:
            current["candidates"] = []
            current["search_error"] = str(exc)
        current["searched"] = True
        selected = current.get("selected_video_id")
        video_ids = {c.get("video_id") for c in current["candidates"]}
        if selected not in video_ids:
            current["selected_video_id"] = None
            if selected:
                current["confirmed"] = False
        updated.append(current)
    return updated
