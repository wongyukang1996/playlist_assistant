"""Build CSV/JSON exports of the verified playlist."""

from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO
from typing import Any

EXPORT_COLUMNS = [
    "playlist_order",
    "original_song_title",
    "original_singer",
    "selected_song_title",
    "selected_artist",
    "album",
    "duration",
    "youtube_music_video_id",
    "youtube_music_url",
]


def _candidate_by_id(track: dict[str, Any]) -> dict[str, Any] | None:
    selected = track.get("selected_video_id")
    if not selected:
        return None
    for candidate in track.get("candidates") or []:
        if candidate.get("video_id") == selected:
            return candidate
    return None


def duplicate_video_ids(tracks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Map video IDs that appear more than once among confirmed, included tracks."""
    groups: dict[str, list[str]] = {}
    for track in verified_tracks(tracks):
        video_id = track.get("selected_video_id")
        if not video_id:
            continue
        groups.setdefault(str(video_id), []).append(str(track.get("id")))
    return {video_id: ids for video_id, ids in groups.items() if len(ids) > 1}


def verified_tracks(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Confirmed tracks that the user has not excluded, in current order."""
    return [
        track
        for track in tracks
        if track.get("confirmed") and track.get("included", True) and track.get("selected_video_id")
    ]


def playlist_rows(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order, track in enumerate(verified_tracks(tracks), start=1):
        candidate = _candidate_by_id(track) or {}
        rows.append(
            {
                "playlist_order": order,
                "original_song_title": track.get("original_title"),
                "original_singer": track.get("original_singer"),
                "selected_song_title": candidate.get("title"),
                "selected_artist": candidate.get("artists"),
                "album": candidate.get("album"),
                "duration": candidate.get("duration"),
                "youtube_music_video_id": candidate.get("video_id"),
                "youtube_music_url": candidate.get("url"),
            }
        )
    return rows


def to_dataframe(tracks: list[dict[str, Any]]):
    """pandas table for spreadsheet-oriented review in the UI."""
    import pandas as pd

    rows = playlist_rows(tracks)
    if not rows:
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def to_csv_bytes(tracks: list[dict[str, Any]]) -> bytes:
    """UTF-8 CSV with BOM so Excel opens Unicode text correctly."""
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in playlist_rows(tracks):
        writer.writerow(row)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def to_json_bytes(tracks: list[dict[str, Any]]) -> bytes:
    payload = playlist_rows(tracks)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text.encode("utf-8")


def to_excel_compatible_csv_file(tracks: list[dict[str, Any]]) -> BytesIO:
    output = BytesIO(to_csv_bytes(tracks))
    output.seek(0)
    return output
