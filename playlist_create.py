"""Optional unofficial YouTube Music playlist creation via ytmusicapi."""

from __future__ import annotations

import json
from typing import Any

PRIVACY_OPTIONS = ("PRIVATE", "UNLISTED", "PUBLIC")
PLAYLIST_URL = "https://music.youtube.com/playlist?list={playlist_id}"


class PlaylistCreateError(Exception):
    """Raised when an authenticated playlist could not be created."""


def detect_auth_kind(auth_data: dict[str, Any]) -> str:
    keys = {str(key).lower() for key in auth_data}
    if "access_token" in keys or "refresh_token" in keys:
        return "oauth"
    if "cookie" in keys or "authorization" in keys:
        return "browser"
    return "unknown"


def _normalize_auth_data(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlaylistCreateError("Authentication file is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise PlaylistCreateError("Authentication file must be a JSON object.")
    return data


def build_authenticated_client(
    auth_raw: str | bytes,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
):
    from ytmusicapi import YTMusic

    auth_data = _normalize_auth_data(auth_raw)
    kind = detect_auth_kind(auth_data)

    try:
        if kind == "oauth":
            from ytmusicapi import OAuthCredentials

            if not client_id or not client_secret:
                raise PlaylistCreateError(
                    "OAuth authentication requires a Google Cloud OAuth client ID and client secret."
                )
            return YTMusic(
                auth_data,
                oauth_credentials=OAuthCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                ),
            )
        return YTMusic(auth_data)
    except PlaylistCreateError:
        raise
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "authentication" in lowered or "auth" in lowered or "401" in message or "403" in message:
            raise PlaylistCreateError(
                "Authentication failed. The file may be expired, incomplete, or logged out. Generate a new one."
            ) from exc
        raise PlaylistCreateError(f"Could not initialize YouTube Music authentication: {message}") from exc


def create_youtube_music_playlist(
    client: Any,
    title: str,
    description: str,
    privacy_status: str,
    video_ids: list[str],
) -> dict[str, str]:
    if not title.strip():
        raise PlaylistCreateError("Enter a playlist title.")
    if privacy_status not in PRIVACY_OPTIONS:
        raise PlaylistCreateError(
            f"Unsupported privacy option. Choose one of: {', '.join(PRIVACY_OPTIONS)}."
        )
    if not video_ids:
        raise PlaylistCreateError("There are no confirmed tracks to add.")

    try:
        result = client.create_playlist(
            title.strip(),
            description.strip(),
            privacy_status=privacy_status,
            video_ids=video_ids,
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        if "provide authentication" in message.lower():
            raise PlaylistCreateError(
                "Playlist creation requires authentication. Search and export still work without it."
            ) from exc
        raise PlaylistCreateError(f"Playlist creation failed: {message}") from exc

    if isinstance(result, str) and result:
        playlist_id = result
        if playlist_id.startswith("VL"):
            playlist_id = playlist_id[2:]
        return {
            "playlist_id": playlist_id,
            "url": PLAYLIST_URL.format(playlist_id=playlist_id),
        }

    raise PlaylistCreateError(
        "YouTube Music did not return a playlist ID. The unofficial library may have changed, "
        f"or the request failed. Response: {result!r}"
    )
