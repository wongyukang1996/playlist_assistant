"""Playlist Assistant (Version 2).
test youtube description: https://www.youtube.com/watch?v=5ZTjMGlF5v8&t=343s
test youtube timeline: https://www.youtube.com/watch?v=OIPXLl6B7Cg
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from export import duplicate_video_ids, to_csv_bytes, to_dataframe, to_json_bytes, verified_tracks
from parser import parse_song_list
from playlist_create import (
    PRIVACY_OPTIONS,
    PlaylistCreateError,
    build_authenticated_client,
    create_youtube_music_playlist,
)
from song_extraction import (
    ORDER_ARTIST_TITLE,
    ORDER_TITLE_ARTIST,
    run_extraction,
    songs_to_entries,
    extract_from_description_comments,
    dedupe_songs,
)
from search import search_candidates, SearchError

SAMPLE_LIST = """# One song per line: Song, Singer  |  Song - Singer  |  Song<TAB>Singer
晴天, 周杰伦
Shape of You, Ed Sheeran
夜曲 - 周杰伦
稻香, 周杰伦
"""


def init_state() -> None:
    defaults: dict[str, Any] = {
        "input_text": SAMPLE_LIST,
        "tracks": [],
        "malformed": [],
        "parse_version": 0,
        "playlist_result": None,
        "playlist_error": None,
        "input_mode": "Text list",
        "video_url": "https://www.youtube.com/watch?v=5ZTjMGlF5v8&t=343s",
        "extraction": None,
        "tracklist_format": "Song - Artist",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource(show_spinner=False)
def unauthenticated_client():
    from ytmusicapi import YTMusic

    return YTMusic()


def track_identity(line_number: int, title: str, singer: str) -> tuple[int, str, str]:
    return (line_number, title, singer)


def merge_tracks(parsed_valid: list) -> list[dict[str, Any]]:
    previous = {
        track_identity(t["line_number"], t["original_title"], t["original_singer"]): t
        for t in st.session_state.tracks
    }
    merged: list[dict[str, Any]] = []
    for entry in parsed_valid:
        key = track_identity(entry.line_number, entry.title, entry.singer)
        old = previous.get(key)
        if old:
            track = dict(old)
            track["raw"] = entry.raw
            merged.append(track)
            continue
        merged.append(
            {
                "id": f"{entry.line_number}:{entry.title}:{entry.singer}",
                "line_number": entry.line_number,
                "original_title": entry.title,
                "original_singer": entry.singer,
                "raw": entry.raw,
                "candidates": [],
                "selected_video_id": None,
                "confirmed": False,
                "included": True,
                "search_error": None,
                "searched": False,
            }
        )
    return merged


def selected_candidate(track: dict[str, Any]) -> dict[str, Any] | None:
    selected = track.get("selected_video_id")
    for candidate in track.get("candidates") or []:
        if candidate.get("video_id") == selected:
            return candidate
    return None


def move_track(track_id: str, delta: int) -> None:
    tracks = list(st.session_state.tracks)
    ids = [t["id"] for t in tracks]
    try:
        index = ids.index(track_id)
    except ValueError:
        return
    new_index = index + delta
    if new_index < 0 or new_index >= len(tracks):
        return
    tracks[index], tracks[new_index] = tracks[new_index], tracks[index]
    st.session_state.tracks = tracks


def search_one(track: dict[str, Any]) -> dict[str, Any]:
    updated = dict(track)
    try:
        client = unauthenticated_client()
        updated["candidates"] = search_candidates(
            client,
            updated["original_title"],
            updated["original_singer"],
        )
        updated["search_error"] = None
    except SearchError as exc:
        updated["candidates"] = []
        updated["search_error"] = str(exc)
    except Exception as exc:
        updated["candidates"] = []
        updated["search_error"] = f"YouTube Music search failed: {exc}"
    updated["searched"] = True
    selected = updated.get("selected_video_id")
    video_ids = {c.get("video_id") for c in updated["candidates"]}
    if selected not in video_ids:
        updated["selected_video_id"] = None
        if selected:
            updated["confirmed"] = False
    return updated



def render_candidate_label(candidate: dict[str, Any], index: int) -> str:
    title = candidate.get("title") or "(title unavailable)"
    artists = candidate.get("artists") or "(artist unavailable)"
    album = candidate.get("album") or "(album unavailable)"
    duration = candidate.get("duration") or "(duration unavailable)"
    return f"{index}. {title} — {artists} | {album} | {duration}"

def reset_for_mode_change() -> None:
    st.session_state.tracks = []
    st.session_state.malformed = []
    st.session_state.playlist_result = None
    st.session_state.playlist_error = None
    st.session_state.parse_version += 1
    st.session_state.extraction = None

def render_export(export_tracks: list[dict[str, Any]]) -> None:
    csv_bytes = to_csv_bytes(st.session_state.tracks)
    json_bytes = to_json_bytes(st.session_state.tracks)
    dl1, dl2, _ = st.columns([1, 1, 2])
    with dl1:
        st.download_button("Download CSV", data=csv_bytes, file_name="playlist.csv",
                           mime="text/csv", disabled=not export_tracks)
    with dl2:
        st.download_button("Download JSON", data=json_bytes, file_name="playlist.json",
                           mime="application/json", disabled=not export_tracks)
    if export_tracks:
        st.dataframe(to_dataframe(st.session_state.tracks), hide_index=True)
    else:
        st.caption("Confirm and include at least one track to enable export.")


def render_ytmusic_create(export_tracks: list[dict[str, Any]]) -> None:
    st.info(
        "This uses **ytmusicapi**, an unofficial integration that is not a Google-supported "
        "YouTube Music playlist API. Compatibility is not guaranteed. Search and CSV/JSON "
        "export do **not** require authentication."
    )
    st.markdown(
        """
Authentication files contain session secrets. **Do not share them or commit them to Git.**

1. Read the current docs: [ytmusicapi documentation](https://ytmusicapi.readthedocs.io/).
2. **Browser file (typical):** log into [music.youtube.com](https://music.youtube.com), copy request headers from an authenticated `browse` POST, then run `ytmusicapi browser` and save `browser.json`.
3. **OAuth file:** as of late 2024 this also needs a Google Cloud OAuth client (TVs and Limited Input devices). Run `ytmusicapi oauth` to create `oauth.json`, then provide the client ID and secret below.
"""
    )
    auth_file = st.file_uploader(
        "Authentication JSON (browser.json or oauth.json)",
        type=["json"],
        help="Kept in memory for this request only. Never hardcoded.",
    )
    oauth_id = st.text_input("OAuth client ID (only if using oauth.json)")
    oauth_secret = st.text_input("OAuth client secret (only if using oauth.json)", type="password")
    playlist_title = st.text_input("Playlist title", value="Playlist Assistant")
    playlist_description = st.text_area("Playlist description", value="")
    privacy = st.selectbox("Privacy", options=list(PRIVACY_OPTIONS), index=0)

    if st.button("Create YouTube Music playlist", disabled=not export_tracks):
        st.session_state.playlist_result = None
        st.session_state.playlist_error = None
        if auth_file is None:
            st.session_state.playlist_error = (
                "Upload an authentication JSON file generated with ytmusicapi. "
                "Search and export still work without it."
            )
            return
        video_ids = [t["selected_video_id"] for t in export_tracks if t.get("selected_video_id")]
        try:
            client = build_authenticated_client(
                auth_file.getvalue(),
                client_id=oauth_id.strip() or None,
                client_secret=oauth_secret.strip() or None,
            )
            st.session_state.playlist_result = create_youtube_music_playlist(
                client, playlist_title, playlist_description, privacy, video_ids
            )
        except PlaylistCreateError as exc:
            st.session_state.playlist_error = str(exc)
        except Exception as exc:
            st.session_state.playlist_error = (
                f"Playlist creation failed ({exc.__class__.__name__}): {exc}"
            )

def render_extraction_results() -> None:
    result = st.session_state.extraction

    if not result:
        return

    if result.get("error"):
        st.error(result["error"])
        return

    st.markdown(
        f"**Video:** {result.get('title') or '(title unavailable)'}"
    )
    st.caption(f"URL: {result['url']}")

    if result.get("fetch_error"):
        st.error(
            f"Video details could not be loaded: {result['fetch_error']}"
        )

    # Start with the methods already run by run_extraction().
    display_methods = list(result.get("methods", []))

    # Re-render Method 2 on every Streamlit rerun.
    # This keeps the editable table visible when checkboxes or cells change.
    meta = result.get("meta")
    order = result.get("order", ORDER_TITLE_ARTIST)

    if meta:
        try:
            method2_result = extract_from_description_comments(meta, order)
            display_methods.append(method2_result)
        except Exception as exc:
            st.error(
                "Description/comments extraction failed: "
                f"{exc.__class__.__name__}: {exc}"
            )
    else:
        # Show Method 2's failure if video metadata could not be loaded.
        display_methods.append({
            "label": "Description and comments",
            "status": "failed",
            "message": result.get(
                "fetch_error",
                "Video metadata is unavailable."
            ),
            "warnings": [],
            "songs": [],
        })

    # Display the status of each extraction method.
    for method in display_methods:
        count = len(method.get("songs", []))

        if method["status"] == "found":
            st.success(
                f"{method['label']}: {count} song(s) found"
            )
        elif method["status"] == "empty":
            st.info(
                f"{method['label']}: ran successfully but found no songs"
            )
        elif method["status"] == "failed":
            st.error(
                f"{method['label']}: failed. "
                f"{method.get('message', 'Unknown error')}"
            )
        elif method["status"] == "review":
            st.info(
                f"{method['label']}: select the song lines you want "
                "and confirm your selection below."
            )
        else:
            st.caption(
                f"{method['label']}: not implemented yet (placeholder)"
            )

        for warning in method.get("warnings", []):
            st.warning(warning)

    # Combine songs from all methods, including the current Method 2 state.
    songs = dedupe_songs([
        song
        for method in display_methods
        for song in method.get("songs", [])
    ])

    # Keep the saved result updated with the latest combined songs.
    result["songs"] = songs

    # Display the combined song list.
    if songs:
        st.markdown(
            f"**Combined list: {len(songs)} song(s)** "
            "(duplicates merged)"
        )

        st.dataframe(
            [
                {
                    "#": i,
                    "Title": song["title"],
                    "Artist": song["artist"] or "—",
                    "Timestamp": song["timestamp"] or "—",
                    "Found by": ", ".join(song["sources"]),
                }
                for i, song in enumerate(songs, start=1)
            ],
            hide_index=True,
        )
    else:
        st.warning(
            "No songs were found by any implemented method. "
            "Select and confirm songs in Method 2, or try another "
            "video URL or switch Input source to Text list."
        )

    # Continue to song verification using the combined results.
    if st.button(
        "Continue to Song Verification",
        type="primary",
        disabled=not songs,
        key="continue_verification",
    ):
        st.session_state.tracks = merge_tracks(
            songs_to_entries(songs)
        )
        st.session_state.parse_version += 1
        st.session_state.playlist_result = None
        st.session_state.playlist_error = None
        
def main() -> None:
    st.set_page_config(page_title="Playlist Assistant", layout="wide")
    init_state()

    st.title("Playlist Assistant")
    st.caption(
        "Version 1 — paste a song list, search YouTube Music, confirm recordings, then export. "
        "Playlist creation uses the unofficial ytmusicapi library and is optional."
    )

    st.subheader("1. Input")
    st.radio(
        "Input source",
        ["Text list", "YouTube link"],
        horizontal=True,
        key="input_mode",
        on_change=reset_for_mode_change,
    )
    mode = st.session_state.input_mode

    if mode == "Text list":
        st.text_area(
            "Paste songs (one per line)",
            key="input_text",
            height=180,
            help="Formats: Song, Singer  |  Song - Singer  |  Song then Tab then Singer. Lines starting with # are comments.",
        )
        if st.button("Parse song list", type="primary"):
            valid, malformed = parse_song_list(st.session_state.input_text)
            st.session_state.tracks = merge_tracks(valid)
            st.session_state.malformed = [item.to_dict() for item in malformed]
            st.session_state.parse_version += 1
            st.session_state.playlist_result = None
            st.session_state.playlist_error = None
    else:
        st.text_input(
            "YouTube video URL",
            key="video_url",
            placeholder="https://www.youtube.com/watch?v=...",
        )

        st.selectbox(
            "Tracklist format",
            ["Song - Artist", "Artist - Song"],
            key="tracklist_format",
            help="How lines like '03:25 A - B' are split. You can still fix any entry during verification.",
        )

        if st.button("Extract songs", type="primary"):
            order = (
                ORDER_ARTIST_TITLE
                if st.session_state.tracklist_format == "Artist - Song"
                else ORDER_TITLE_ARTIST
            )

            with st.spinner("Inspecting video…"):
                st.session_state.extraction = run_extraction(
                    st.session_state.video_url,
                    order,
                )

            st.session_state.tracks = []
            st.session_state.malformed = []
            st.session_state.parse_version += 1
            st.session_state.playlist_result = None
            st.session_state.playlist_error = None

        # Render saved results on every Streamlit rerun.
        if st.session_state.extraction:
            render_extraction_results()

    malformed = st.session_state.malformed
    tracks = st.session_state.tracks
    if malformed:
        st.warning(f"{len(malformed)} malformed line(s) were skipped. Other valid lines were kept.")
        for item in malformed:
            st.markdown(
                f"- Line {item['line_number']}: `{item['raw']}` — {item['error']}"
            )
    if tracks:
        st.success(f"Loaded {len(tracks)} song(s). You can edit the input and load again.")
    st.subheader("2. Search")
    st.write(
        "Searches run live against YouTube Music (unauthenticated). "
        "The first result is never selected automatically."
    )
    if st.button("Search YouTube Music for all parsed songs", disabled=not tracks):
        progress = st.progress(0.0, text="Starting search…")
        status = st.empty()
        updated: list[dict[str, Any]] = []
        total = len(st.session_state.tracks)
        for index, track in enumerate(st.session_state.tracks, start=1):
            status.write(
                f"Searching {index}/{total}: {track['original_title']} — {track['original_singer']}"
            )
            updated.append(search_one(track))
            progress.progress(index / total, text=f"Searched {index} of {total}")
            st.session_state.tracks = updated + st.session_state.tracks[index:]
        st.session_state.tracks = updated
        progress.progress(1.0, text="Search complete")
        status.empty()
        st.rerun()

        tracks = st.session_state.tracks
        
        st.subheader("2. Search")
        st.write(
            "Searches run live against YouTube Music (unauthenticated). "
            "The first result is never selected automatically."
        )
        if st.button("Search YouTube Music for all parsed songs", disabled=not tracks):
            ...  # existing search loop, unchanged, indented one level
            st.rerun()

        tracks = st.session_state.tracks
        searched = [t for t in tracks if t.get("searched")]
        empty_results = [t for t in searched if not t.get("candidates") and not t.get("search_error")]
        errored = [t for t in searched if t.get("search_error")]
        if searched:
            st.info(f"Live search finished for {len(searched)} of {len(tracks)} parsed song(s).")
        if empty_results:
            st.warning(
                f"{len(empty_results)} song(s) returned no candidates. Edit the title/singer below and search again."
            )
        if errored:
            st.error(f"{len(errored)} search(es) failed. See details on each track.")

    tracks = st.session_state.tracks
    st.subheader("3. Verification")
    st.write(
        "Select a candidate and tick **Confirm this recording**. "
        "Only confirmed tracks can enter the playlist. Leave a track unconfirmed if none of the results is correct."
    )
    if not tracks:
        st.caption("Parse a song list to start verification.")

    for track in tracks:
        tid = track["id"]
        header = (
            f"Line {track['line_number']}: {track['original_title']} — {track['original_singer']}"
        )
        if track.get("confirmed"):
            header += " ✓ confirmed"
        with st.expander(header, expanded=not track.get("confirmed")):
            st.caption(f"Original input: `{track.get('raw', '')}`")
            col_a, col_b, col_c = st.columns([2, 2, 1])
            with col_a:
                new_title = st.text_input(
                    "Song title",
                    value=track["original_title"],
                    key=f"title_{tid}_{st.session_state.parse_version}",
                )
            with col_b:
                new_singer = st.text_input(
                    "Singer",
                    value=track["original_singer"],
                    key=f"singer_{tid}_{st.session_state.parse_version}",
                )
            with col_c:
                st.write("")
                if st.button("Search again", key=f"research_{tid}"):
                    track["original_title"] = new_title.strip() or track["original_title"]
                    track["original_singer"] = new_singer.strip() or track["original_singer"]
                    replacement = search_one(track)
                    st.session_state.tracks = [
                        replacement if item["id"] == tid else item for item in st.session_state.tracks
                    ]
                    st.rerun()

            if track.get("search_error"):
                st.error(track["search_error"])
            elif not track.get("searched"):
                st.info("Not searched yet. Use the batch search button above, or Search again here.")
            elif not track.get("candidates"):
                st.warning("No YouTube Music candidates. Adjust the title/singer and search again.")
            else:
                options = [c["video_id"] for c in track["candidates"]]
                labels = {
                    c["video_id"]: render_candidate_label(c, i)
                    for i, c in enumerate(track["candidates"], start=1)
                }
                previous = track.get("selected_video_id")
                if previous not in options:
                    previous = None
                selected = st.radio(
                    "Candidates (live YouTube Music results)",
                    options=options,
                    index=options.index(previous) if previous in options else None,
                    format_func=lambda vid, labels=labels: labels[vid],
                    key=f"radio_{tid}",
                )
                if selected != previous:
                    st.session_state[f"confirm_{tid}"] = False
                track["selected_video_id"] = selected
                candidate = selected_candidate(track)
                if candidate and candidate.get("url"):
                    st.link_button("Open selected candidate in YouTube Music", candidate["url"])
                    meta_cols = st.columns(4)
                    meta_cols[0].markdown(f"**Title**  \n{candidate.get('title') or '—'}")
                    meta_cols[1].markdown(f"**Artist**  \n{candidate.get('artists') or '—'}")
                    meta_cols[2].markdown(f"**Album**  \n{candidate.get('album') or '—'}")
                    meta_cols[3].markdown(f"**Duration**  \n{candidate.get('duration') or '—'}")
                    st.caption(f"Video ID: `{candidate.get('video_id')}`")

                confirmed = st.checkbox(
                    "Confirm this recording",
                    value=bool(track.get("confirmed") and track.get("selected_video_id") == selected),
                    key=f"confirm_{tid}",
                    disabled=not selected,
                )
                track["confirmed"] = bool(confirmed and selected)
                if track["confirmed"] and not track.get("included"):
                    # Newly confirmed tracks are included until the user excludes them.
                    if f"include_{tid}" not in st.session_state:
                        track["included"] = True

    # Persist widget-driven fields back into session_state.tracks
    st.session_state.tracks = tracks

    st.subheader("4. Playlist")
    confirmed = verified_tracks(st.session_state.tracks)
    unconfirmed = [
        t for t in st.session_state.tracks if not (t.get("confirmed") and t.get("selected_video_id"))
    ]
    excluded = [
        t
        for t in st.session_state.tracks
        if t.get("confirmed") and t.get("selected_video_id") and not t.get("included", True)
    ]

    st.write(
        f"Confirmed and included: **{len(confirmed)}** · "
        f"Unconfirmed: **{len(unconfirmed)}** · "
        f"Excluded: **{len(excluded)}**"
    )

    dupes = duplicate_video_ids(st.session_state.tracks)
    if dupes:
        st.warning(
            "Possible duplicate recordings (same YouTube Music video ID). "
            "Nothing was deleted automatically."
        )
        for video_id, ids in dupes.items():
            titles = [
                f"{t['original_title']} — {t['original_singer']}"
                for t in st.session_state.tracks
                if t["id"] in ids
            ]
            st.markdown(f"- `{video_id}`: " + "; ".join(titles))

    if not st.session_state.tracks:
        st.caption("Confirmed songs will appear here.")

    playlist_ids = [t["id"] for t in st.session_state.tracks]
    for position, track in enumerate(st.session_state.tracks):
        tid = track["id"]
        candidate = selected_candidate(track)
        ready = bool(track.get("confirmed") and track.get("selected_video_id"))
        cols = st.columns([0.6, 2.2, 2.2, 1.2, 1.4, 1.2])
        cols[0].write(str(position + 1))
        cols[1].write(f"{track['original_title']} — {track['original_singer']}")
        if candidate:
            cols[2].write(f"{candidate.get('title') or '—'} — {candidate.get('artists') or '—'}")
        else:
            cols[2].write("No confirmed selection")
        cols[3].write("Confirmed" if ready else "Unconfirmed")
        if ready:
            include_key = f"include_{tid}"
            if include_key not in st.session_state:
                st.session_state[include_key] = bool(track.get("included", True))
            track["included"] = cols[4].checkbox("Include", key=include_key)
        else:
            cols[4].caption("Confirm first")
            track["included"] = True
        with cols[5]:
            up, down = st.columns(2)
            if up.button("↑", key=f"up_{tid}", disabled=position == 0):
                move_track(tid, -1)
                st.rerun()
            if down.button("↓", key=f"down_{tid}", disabled=position == len(playlist_ids) - 1):
                move_track(tid, 1)
                st.rerun()
        if ready and candidate and candidate.get("url"):
            st.caption(
                f"Album: {candidate.get('album') or '—'} · "
                f"Duration: {candidate.get('duration') or '—'} · "
                f"[Open in YouTube Music]({candidate['url']})"
            )

    st.session_state.tracks = tracks

    st.subheader("5. Export or create")
    export_tracks = verified_tracks(st.session_state.tracks)
    dest = st.radio(
        "What do you want to do?",
        ["Export file", "Create YouTube Music playlist"],
        horizontal=True,
        key="destination",
    )
    if dest == "Export file":
        render_export(export_tracks)
    else:
        render_ytmusic_create(export_tracks)

    if st.session_state.playlist_error:
        st.error(st.session_state.playlist_error)
    if st.session_state.playlist_result:
        result = st.session_state.playlist_result
        st.success("Playlist created.")
        st.markdown(f"[Open playlist in YouTube Music]({result['url']})")
        st.caption(f"Playlist ID: `{result['playlist_id']}`")


if __name__ == "__main__":
    main()
