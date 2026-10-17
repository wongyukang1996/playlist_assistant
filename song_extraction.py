"""Identify songs in a single YouTube video.

Method 1: chapters / timeline metadata   -> extract_from_timestamps
Method 2: description and comments       -> extract_from_description_comments
Method 3: AI identification (placeholder)-> identify_songs_with_ai
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from video_import import extract_video_id

SOURCE_TIMESTAMPS = "video_timestamps"
SOURCE_DESCRIPTION_COMMENTS = "description_comments"
SOURCE_AI = "ai_identification"

METHOD_LABELS = {
    SOURCE_TIMESTAMPS: "Method 1: Video timestamps / chapters",
    SOURCE_DESCRIPTION_COMMENTS: "Method 2: Description and comments",
    SOURCE_AI: "Method 3: AI identification",
}

ORDER_TITLE_ARTIST = "title_artist"   # "Song - Artist"
ORDER_ARTIST_TITLE = "artist_title"   # "Artist - Song"

_TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
_LEAD_TS_RE = re.compile(
    rf"^\s*[\[\(]?\s*(?P<ts>{_TS})\s*[\]\)]?\s*[-–—:.|)]*\s*(?P<rest>.*)$"
)
_TRAIL_TS_RE = re.compile(rf"^(?P<rest>.+?)\s+[\[\(]?(?P<ts>{_TS})[\]\)]?\s*$")
_LIST_ITEM_RE = re.compile(
    r"^\s*(?:\d{1,3}[.)]|[•●▪◦♪♫▶►*\-–—])\s+(?P<rest>.+)$"
)
_SEP_RE = re.compile(r"\s+[-–—|]\s+|\s+by\s+", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_NOISE_WORDS = (
    "http", "www.", "instagram", "facebook", "twitter", "tiktok", "patreon",
    "subscribe", "follow me", "copyright", "business inquir", "contact",
)
_NON_SONG_TITLES = {"intro", "outro", "start", "end", "ending", "opening", "tracklist"}


class ExtractionError(Exception):
    """Raised when video metadata cannot be retrieved."""


# --------------------------------------------------------------------------
# Shared parsing helpers
# --------------------------------------------------------------------------

def timestamp_to_seconds(ts: str) -> int:
    total = 0
    for part in ts.split(":"):
        total = total * 60 + int(part)
    return total


def seconds_to_timestamp(seconds: int | float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _clean(text: str) -> str:
    text = re.sub(r"^\s*(?:\d{1,3}[.)]\s+|[•●▪◦♪♫▶►*]+\s*)", "", text)
    return text.strip().strip("-–—|:·").strip()


def split_title_artist(text: str, order: str = ORDER_TITLE_ARTIST) -> tuple[str, str]:
    """Split 'Song - Artist' (or 'Artist - Song', or 'Song by Artist')."""
    text = _clean(text)
    match = _SEP_RE.search(text)
    if not match:
        return text, ""
    left, right = text[: match.start()].strip(), text[match.end():].strip()
    if not left or not right:
        return text, ""
    if match.group().strip().lower() == "by":
        return left, right
    return (left, right) if order == ORDER_TITLE_ARTIST else (right, left)


def make_song(title: str, artist: str, timestamp: str, source: str) -> dict[str, Any] | None:
    title = (title or "").strip()
    if not title or title.lower() in _NON_SONG_TITLES:
        return None
    return {
        "title": title,
        "artist": (artist or "").strip(),
        "timestamp": timestamp or "",
        "source": source,
    }


def _is_noise(text: str) -> bool:
    lowered = text.lower()
    return len(text) > 150 or "?" in text or any(w in lowered for w in _NOISE_WORDS)


def _split_timestamp(line: str) -> tuple[str | None, str]:
    match = _LEAD_TS_RE.match(line)
    if match and match.group("rest").strip():
        ts, rest = match.group("ts"), match.group("rest")
    else:
        match = _TRAIL_TS_RE.match(line)
        if not match:
            return None, ""
        ts, rest = match.group("ts"), match.group("rest")
    seconds = timestamp_to_seconds(ts)
    if seconds >= 86400:
        return None, ""
    return seconds_to_timestamp(seconds), rest


def parse_timestamped_lines(
    text: str, source: str, order: str = ORDER_TITLE_ARTIST
) -> list[dict[str, Any]]:
    """Shared timestamp parser: '00:00 Song - Artist', '[3:25] Song', 'Song 7:10'."""
    songs: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        ts, rest = _split_timestamp(line)
        if not ts or not rest.strip() or _is_noise(rest):
            continue
        title, artist = split_title_artist(rest, order)
        song = make_song(title, artist, ts, source)
        if song:
            songs.append(song)
    return songs


def parse_untimed_list(
    text: str, source: str, order: str = ORDER_TITLE_ARTIST
) -> list[dict[str, Any]]:
    """Numbered or bulleted 'Song - Artist' lines with no timestamps.

    Requires at least 3 matching lines to avoid picking up stray text.
    """
    songs: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        match = _LIST_ITEM_RE.match(line)
        if not match or _is_noise(match.group("rest")):
            continue
        title, artist = split_title_artist(match.group("rest"), order)
        if not artist:
            continue
        song = make_song(title, artist, "", source)
        if song:
            songs.append(song)
    return songs if len(songs) >= 3 else []


# --------------------------------------------------------------------------
# Metadata retrieval
# --------------------------------------------------------------------------

def _friendly_error(exc: Exception) -> str:
    text = _ANSI_RE.sub("", str(exc)).strip()
    lowered = text.lower()
    if "429" in lowered or "too many requests" in lowered or "rate" in lowered and "limit" in lowered:
        return "YouTube is rate-limiting requests. Wait a few minutes and try again."
    if "private video" in lowered:
        return "This video is private."
    if "sign in" in lowered or "age" in lowered and "restrict" in lowered:
        return "This video requires sign-in (age-restricted or members-only)."
    if "unavailable" in lowered or "not available" in lowered or "removed" in lowered:
        return "This video is unavailable (deleted, region-blocked or removed)."
    if "urlopen error" in lowered or "timed out" in lowered or "network" in lowered:
        return f"Network error while contacting YouTube: {text[:200]}"
    return text[:300] or exc.__class__.__name__


def _extract_info(yt_dlp: Any, url: str, options: dict[str, Any]) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def fetch_video_metadata(url: str, max_comments: int = 100) -> dict[str, Any]:
    """Return title, description, chapters and comments for one video.

    Comment failures never fail the whole fetch: they are reported in
    `comments_error` / `comments_note`.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise ExtractionError("yt-dlp is not installed. Run: pip install yt-dlp") from exc

    base = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }
    info = None
    comments_error = None
    try:
        info = _extract_info(
            yt_dlp,
            url,
            {
                **base,
                "getcomments": True,
                "extractor_args": {
                    "youtube": {"max_comments": [str(max_comments)], "comment_sort": ["top"]}
                },
            },
        )
    except Exception as exc:
        comments_error = _friendly_error(exc)

    if info is None:
        try:
            info = _extract_info(yt_dlp, url, base)
        except Exception as exc:
            raise ExtractionError(_friendly_error(exc)) from exc

    comments = info.get("comments") or []
    comments_note = None
    if not comments and comments_error is None:
        comments_note = "No comments were returned (comments may be disabled or unavailable)."

    return {
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "chapters": info.get("chapters") or [],
        "comments": comments,
        "comments_error": comments_error,
        "comments_note": comments_note,
    }


# --------------------------------------------------------------------------
# Result helper
# --------------------------------------------------------------------------

def _result(
    key: str,
    status: str,
    songs: list[dict[str, Any]] | None = None,
    message: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """status: found | empty | failed | not_implemented"""
    return {
        "key": key,
        "label": METHOD_LABELS[key],
        "status": status,
        "songs": songs or [],
        "message": message,
        "warnings": warnings or [],
    }


# --------------------------------------------------------------------------
# Method 1: timestamps / chapters
# --------------------------------------------------------------------------

def extract_from_timestamps(meta: dict[str, Any], order: str = ORDER_TITLE_ARTIST) -> dict[str, Any]:
    songs: list[dict[str, Any]] = []
    chapters = meta.get("chapters") or []
    for chapter in chapters:
        title, artist = split_title_artist(chapter.get("title") or "", order)
        song = make_song(title, artist, seconds_to_timestamp(chapter.get("start_time") or 0),
                         SOURCE_TIMESTAMPS)
        if song:
            songs.append(song)
    if songs:
        return _result(SOURCE_TIMESTAMPS, "found", songs)
    warnings = [] if chapters else ["This video has no chapters or timeline metadata."]
    return _result(SOURCE_TIMESTAMPS, "empty", warnings=warnings)


# --------------------------------------------------------------------------
# Method 2: description and comments
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Method 2: description and popular comments with manual line selection
# --------------------------------------------------------------------------

import re
import unicodedata
from typing import Any

import pandas as pd
import streamlit as st


def _normalize_source_text(text: str) -> str:
    """Normalize text while preserving the original song wording."""
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _get_comment_likes(comment: dict[str, Any]) -> int:
    """Support common comment like-count field names."""
    for key in ("like_count", "likeCount", "likes"):
        try:
            return int(comment.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _split_line_for_editing(line: str) -> tuple[str, str, str | None]:
    """
    Best-effort prefill only. The user can edit all fields.

    Supports:
      《大田后生仔》 林启得
      【爱情恰恰】陈小云
      爱情恰恰 - 陈小云
      爱情恰恰：陈小云
    """
    line = line.strip()
    timestamp = None

    # Extract a leading timestamp such as 03:25 or 1:02:30.
    match = re.match(
        r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—.]?\s*(.*)$",
        line,
    )
    if match:
        timestamp = match.group(1)
        line = match.group(2).strip()

    # Title enclosed in Chinese-style brackets.
    match = re.match(
        r"^[《【「『〈](.+?)[》】」』〉]\s*(.*)$",
        line,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip(), timestamp

    # Explicit separators: title - artist, title: artist, title / artist.
    match = re.match(r"^(.+?)\s*[-–—:：|/]\s*(.+)$", line)
    if match:
        return match.group(1).strip(), match.group(2).strip(), timestamp

    # Do not guess a boundary for unseparated text.
    return "", "", timestamp


def extract_description_comment_lines(
    meta: dict[str, Any],
    max_comments: int = 10,
) -> dict[str, Any]:
    """
    Collect every non-empty description line and lines from the most
    popular top-level comments.

    Pinned comments are included even if they are outside the like-count
    top list. The remaining comments are sorted by likes.
    """
    src = SOURCE_DESCRIPTION_COMMENTS
    warnings: list[str] = []
    lines: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_text_lines(
        text: str,
        source_type: str,
        source_label: str,
        likes: int = 0,
        pinned: bool = False,
    ) -> None:
        text = _normalize_source_text(text)

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            raw_line = raw_line.strip()

            if not raw_line:
                continue

            # Deduplicate exact lines from the same source category.
            key = (source_type, re.sub(r"\s+", " ", raw_line).casefold())
            if key in seen:
                continue
            seen.add(key)

            title, artist, timestamp = _split_line_for_editing(raw_line)

            lines.append({
                "Include": False,
                "Original line": raw_line,
                "Title": title,
                "Artist": artist,
                "Timestamp": timestamp or "",
                "Source": source_label,
                "Likes": likes,
                "_line_number": line_number,
            })

    # 1. Collect every non-empty description line.
    description = meta.get("description") or ""

    if description.strip():
        add_text_lines(
            description,
            source_type="description",
            source_label="Description",
        )
    else:
        warnings.append("This video has no description.")

    # 2. Select popular top-level comments.
    comments_error = meta.get("comments_error")

    if comments_error:
        warnings.append(
            f"Comments could not be retrieved: {comments_error}"
        )
    elif meta.get("comments_note"):
        warnings.append(str(meta["comments_note"]))

    comments = [
        comment
        for comment in (meta.get("comments") or [])
        if isinstance(comment, dict)
        and comment.get("parent") in (None, "root")
        and (comment.get("text") or "").strip()
    ]

    pinned_comments = [
        comment for comment in comments
        if comment.get("is_pinned")
    ]

    non_pinned_comments = [
        comment for comment in comments
        if not comment.get("is_pinned")
    ]

    # Sort by likes, highest first.
    non_pinned_comments.sort(
        key=_get_comment_likes,
        reverse=True,
    )

    # Include pinned comments plus the most-liked non-pinned comments.
    selected_comments = pinned_comments + non_pinned_comments[:max_comments]

    for index, comment in enumerate(selected_comments, start=1):
        comment_label = (
            "Pinned comment"
            if comment.get("is_pinned")
            else f"Popular comment {index}"
        )

        add_text_lines(
            comment.get("text") or "",
            source_type="comment",
            source_label=comment_label,
            likes=_get_comment_likes(comment),
            pinned=bool(comment.get("is_pinned")),
        )

    return {
        "source": src,
        "status": "found" if lines else "empty",
        "lines": lines,
        "warnings": warnings,
    }


import hashlib
import json
import pandas as pd
import streamlit as st
from typing import Any


def extract_from_description_comments(
    meta: dict[str, Any],
    order: str = ORDER_TITLE_ARTIST,
    max_comments: int = 10,
) -> dict[str, Any]:

    src = SOURCE_DESCRIPTION_COMMENTS

    # Create a stable key for this video's extraction.
    # This prevents the table state from being lost on checkbox reruns.
    source_signature = json.dumps(
        {
            "video_id": (
                meta.get("video_id")
                or meta.get("videoId")
                or meta.get("url")
                or ""
            ),
            "description": meta.get("description") or "",
            "comments": [
                {
                    "text": c.get("text") or "",
                    "likes": _get_comment_likes(c),
                    "pinned": bool(c.get("is_pinned")),
                    "parent": c.get("parent"),
                }
                for c in (meta.get("comments") or [])
                if isinstance(c, dict)
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    video_key = hashlib.sha1(
        source_signature.encode("utf-8")
    ).hexdigest()[:12]

    lines_key = f"method2_lines_{video_key}"
    editor_key = f"method2_editor_{video_key}"
    confirmed_key = f"method2_confirmed_{video_key}"

    # If the user already confirmed the tracks, preserve the result.
    if confirmed_key in st.session_state:
        return _result(
            src,
            "found",
            st.session_state[confirmed_key],
            warnings=st.session_state.get(
                f"method2_warnings_{video_key}", []
            ),
        )

    # Extract lines only once per video/content.
    # Do not rebuild the dataframe every time a checkbox changes.
    if lines_key not in st.session_state:
        collected = extract_description_comment_lines(
            meta,
            max_comments=max_comments,
        )

        st.session_state[lines_key] = collected["lines"]
        st.session_state[f"method2_warnings_{video_key}"] = (
            collected["warnings"]
        )

    lines = st.session_state[lines_key]
    warnings = st.session_state.get(
        f"method2_warnings_{video_key}", []
    )

    st.subheader("Method 2: Description and comments")
    st.caption(
        "Tick the lines containing songs. Edit the title and artist "
        "if needed. Your selections will remain when the page reruns."
    )

    for warning in warnings:
        st.warning(warning)

    if not lines:
        st.info("No non-empty lines were found.")
        return _result(src, "empty", warnings=warnings)

    st.write(f"Collected **{len(lines)} unique lines**.")

    # Initialize the editor data only once.
    # Streamlit will then manage checkbox and text edits under editor_key.
    if editor_key not in st.session_state:
        df = pd.DataFrame(lines)

        columns = [
            "Include",
            "Original line",
            "Title",
            "Artist",
            "Timestamp",
            "Source",
            "Likes",
        ]

        st.session_state[editor_key] = df[columns].copy()

    edited_df = st.data_editor(
        st.session_state[editor_key],
        key=f"{editor_key}_widget",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "Include": st.column_config.CheckboxColumn(
                "Song?",
                help="Tick to select this line as a song.",
                default=False,
            ),
            "Original line": st.column_config.TextColumn(
                "Original line",
                disabled=True,
                width="large",
            ),
            "Title": st.column_config.TextColumn(
                "Song title",
                help="Edit the song title.",
                width="medium",
            ),
            "Artist": st.column_config.TextColumn(
                "Artist(s)",
                help="Edit the artist name(s).",
                width="medium",
            ),
            "Timestamp": st.column_config.TextColumn(
                "Timestamp",
                help="Optional video timestamp.",
                width="small",
            ),
            "Source": st.column_config.TextColumn(
                "Found in",
                disabled=True,
                width="small",
            ),
            "Likes": st.column_config.NumberColumn(
                "Likes",
                disabled=True,
                width="small",
            ),
        },
    )

    # Keep the latest editor values in session state.
    # On a checkbox change, Streamlit reruns and restores the table.
    st.session_state[editor_key] = edited_df.copy()

    col1, col2 = st.columns(2)

    with col1:
        confirm_clicked = st.button(
            "Confirm selected songs",
            key=f"confirm_{video_key}",
            type="primary",
        )

    with col2:
        reset_clicked = st.button(
            "Clear selections",
            key=f"clear_{video_key}",
        )

    if reset_clicked:
        # Reset the editor and remove any previous confirmation.
        st.session_state.pop(editor_key, None)
        st.session_state.pop(confirmed_key, None)
        st.rerun()

    if not confirm_clicked:
        st.info(
            "Select your song lines above, then click "
            "**Confirm selected songs**."
        )
        return _result(src, "review", warnings=warnings)

    selected = edited_df[edited_df["Include"].fillna(False)]

    confirmed_songs: list[dict[str, Any]] = []
    missing_fields: list[str] = []

    for _, row in selected.iterrows():
        title = str(row.get("Title") or "").strip()
        artist = str(row.get("Artist") or "").strip()
        original_line = str(row.get("Original line") or "").strip()
        timestamp = str(row.get("Timestamp") or "").strip()

        if not title or not artist:
            missing_fields.append(original_line)
            continue

        confirmed_songs.append({
            "title": title,
            "artist": artist,
            "timestamp": timestamp or None,
            "source": src,
            "original_text": original_line,
        })

    if missing_fields:
        st.warning(
            f"{len(missing_fields)} selected line(s) need both a title "
            "and artist. Fill in the missing fields and confirm again."
        )
        return _result(src, "review", warnings=warnings)

    if not confirmed_songs:
        st.warning("Please tick at least one song line.")
        return _result(src, "review", warnings=warnings)

    # Persist the confirmed result so later reruns do not lose it.
    st.session_state[confirmed_key] = confirmed_songs

    st.success(f"Confirmed {len(confirmed_songs)} song(s).")

    return _result(
        src,
        "found",
        confirmed_songs,
        warnings=warnings,
    )
# --------------------------------------------------------------------------
# Method 3: AI identification (placeholder, intentionally empty)
# --------------------------------------------------------------------------

def identify_songs_with_ai(video_url: str) -> list[dict]:
    """Placeholder for future AI-based song identification."""
    return []


# --------------------------------------------------------------------------
# Combine, dedupe, order
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").lower())


def dedupe_songs(songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge obvious duplicates, keeping timestamp, artist and every source."""
    merged: list[dict[str, Any]] = []
    for song in songs:
        title, artist = _norm(song["title"]), _norm(song["artist"])
        match = None
        for existing in merged:
            existing_artist = _norm(existing["artist"])
            if _norm(existing["title"]) == title and (
                not artist or not existing_artist or artist == existing_artist
            ):
                match = existing
                break
        if match is None:
            entry = dict(song)
            entry["sources"] = [song["source"]]
            merged.append(entry)
            continue
        if not match["artist"] and song["artist"]:
            match["artist"] = song["artist"]
        if not match["timestamp"] and song["timestamp"]:
            match["timestamp"] = song["timestamp"]
        if song["source"] not in match["sources"]:
            match["sources"].append(song["source"])

    def sort_key(song: dict[str, Any]) -> tuple[int, int]:
        if song["timestamp"]:
            return (0, timestamp_to_seconds(song["timestamp"]))
        return (1, 0)  # stable sort keeps original order for untimed songs

    return sorted(merged, key=sort_key)


# --------------------------------------------------------------------------
# Workflow
# --------------------------------------------------------------------------

def run_extraction(url: str, order: str = ORDER_TITLE_ARTIST) -> dict[str, Any]:
    url = (url or "").strip()
    video_id = extract_video_id(url)
    if not video_id:
        return {
            "error": "That is not a valid YouTube video URL. Paste a link like "
                     "https://www.youtube.com/watch?v=... or https://youtu.be/...",
            "url": url,
        }
    canonical = f"https://www.youtube.com/watch?v={video_id}"

    meta: dict[str, Any] | None = None
    fetch_error = None
    try:
        meta = fetch_video_metadata(canonical)
    except ExtractionError as exc:
        fetch_error = str(exc)
    except Exception as exc:
        fetch_error = f"Unexpected error: {exc.__class__.__name__}: {exc}"

    methods: list[dict[str, Any]] = []
    for key, func in (
    (SOURCE_TIMESTAMPS, extract_from_timestamps),
    ):
        if meta is None:
            methods.append(_result(key, "failed", message=f"Could not load video: {fetch_error}"))
            continue
        try:
            methods.append(func(meta, order))
        except Exception as exc:  # one method failing must not stop the others
            methods.append(_result(key, "failed", message=f"{exc.__class__.__name__}: {exc}"))

    try:
        ai_songs = identify_songs_with_ai(canonical) or []
    except Exception:
        ai_songs = []
    methods.append(_result(SOURCE_AI, "not_implemented", ai_songs,
                           message="Placeholder: not implemented yet."))

    combined = dedupe_songs([song for m in methods for song in m["songs"]])
    return {
        "error": None,
        "fetch_error": fetch_error,
        "url": canonical,
        "video_id": video_id,
        "title": (meta or {}).get("title", ""),
        "meta": meta,
        "order": order,
        "methods": methods,
        "songs": combined,
    }


def songs_to_entries(songs: list[dict[str, Any]]) -> list[SimpleNamespace]:
    """Adapt extracted songs to what app.merge_tracks() expects from the TXT parser."""
    entries = []
    for index, song in enumerate(songs, start=1):
        raw = " ".join(p for p in (song["timestamp"], song["title"],
                                   f"- {song['artist']}" if song["artist"] else "") if p)
        entries.append(
            SimpleNamespace(line_number=index, title=song["title"], singer=song["artist"], raw=raw)
        )
    return entries