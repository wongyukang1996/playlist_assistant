import json
import unittest

from export import duplicate_video_ids, playlist_rows, to_csv_bytes, to_json_bytes, verified_tracks
from parser import parse_song_list
from playlist_create import detect_auth_kind
from search import format_candidate, search_candidates, SearchError


class ParserTests(unittest.TestCase):
    def test_supported_formats_and_comments(self):
        text = """
# comment
晴天, 周杰伦
Shape of You, Ed Sheeran
夜曲 - 周杰伦
稻香\t周杰伦

Song Only
, missing title
empty singer,
"""
        valid, malformed = parse_song_list(text)
        self.assertEqual(
            [(row.title, row.singer, row.line_number) for row in valid],
            [
                ("晴天", "周杰伦", 3),
                ("Shape of You", "Ed Sheeran", 4),
                ("夜曲", "周杰伦", 5),
                ("稻香", "周杰伦", 6),
            ],
        )
        self.assertEqual(len(malformed), 3)
        self.assertTrue(all(item.error for item in malformed))

    def test_fullwidth_comma_and_duplicates_allowed(self):
        text = "晴天，周杰伦\n晴天，周杰伦"
        valid, malformed = parse_song_list(text)
        self.assertEqual(len(malformed), 0)
        self.assertEqual(len(valid), 2)
        self.assertEqual(valid[0].title, "晴天")
        self.assertEqual(valid[0].singer, "周杰伦")

    def test_reparse_keeps_valid_when_some_lines_malformed(self):
        valid, malformed = parse_song_list("ok, artist\nbad line")
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(malformed), 1)


class CandidateFormatTests(unittest.TestCase):
    def test_does_not_invent_missing_metadata(self):
        formatted = format_candidate(
            {
                "title": "晴天",
                "videoId": "abc123",
                "artists": [{"name": "周杰伦"}],
            }
        )
        self.assertEqual(formatted["title"], "晴天")
        self.assertEqual(formatted["artists"], "周杰伦")
        self.assertIsNone(formatted["album"])
        self.assertIsNone(formatted["duration"])
        self.assertEqual(formatted["url"], "https://music.youtube.com/watch?v=abc123")

    def test_skips_results_without_video_id(self):
        self.assertIsNone(format_candidate({"title": "Album only", "resultType": "album"}))


class FakeClient:
    def __init__(self, songs=None, mixed=None, error=None):
        self.songs = songs or []
        self.mixed = mixed or []
        self.error = error
        self.calls = []

    def search(self, query, filter=None, limit=20):
        self.calls.append({"query": query, "filter": filter, "limit": limit})
        if self.error:
            raise self.error
        if filter == "songs":
            return self.songs
        return self.mixed


class SearchTests(unittest.TestCase):
    def test_uses_title_and_singer_and_caps_results(self):
        songs = [
            {"title": f"Song {i}", "videoId": f"id{i}", "artists": [{"name": "A"}], "duration": "3:00"}
            for i in range(8)
        ]
        client = FakeClient(songs=songs, mixed=songs)
        results = search_candidates(client, "晴天", "周杰伦")
        self.assertEqual(client.calls[0]["query"], "晴天 周杰伦")
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["video_id"], "id0")

    def test_unexpected_response(self):
        class BadClient:
            def search(self, **kwargs):
                return {"not": "a list"}

        with self.assertRaises(SearchError):
            search_candidates(BadClient(), "a", "b")


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tracks = [
            {
                "id": "1",
                "original_title": "晴天",
                "original_singer": "周杰伦",
                "selected_video_id": "vid1",
                "confirmed": True,
                "included": True,
                "candidates": [
                    {
                        "title": "晴天",
                        "artists": "周杰伦",
                        "album": "叶惠美",
                        "duration": "4:29",
                        "video_id": "vid1",
                        "url": "https://music.youtube.com/watch?v=vid1",
                    }
                ],
            },
            {
                "id": "2",
                "original_title": "Unconfirmed",
                "original_singer": "X",
                "selected_video_id": "vid2",
                "confirmed": False,
                "included": True,
                "candidates": [{"title": "Nope", "video_id": "vid2", "url": "u", "artists": "X", "album": None, "duration": None}],
            },
            {
                "id": "3",
                "original_title": "Excluded",
                "original_singer": "Y",
                "selected_video_id": "vid3",
                "confirmed": True,
                "included": False,
                "candidates": [{"title": "Skip", "video_id": "vid3", "url": "u", "artists": "Y", "album": None, "duration": None}],
            },
            {
                "id": "4",
                "original_title": "Shape of You",
                "original_singer": "Ed Sheeran",
                "selected_video_id": "vid4",
                "confirmed": True,
                "included": True,
                "candidates": [
                    {
                        "title": "Shape of You",
                        "artists": "Ed Sheeran",
                        "album": "Divide",
                        "duration": "3:53",
                        "video_id": "vid4",
                        "url": "https://music.youtube.com/watch?v=vid4",
                    }
                ],
            },
        ]

    def test_export_excludes_unconfirmed_and_excluded_and_keeps_order(self):
        rows = playlist_rows(self.tracks)
        self.assertEqual([row["playlist_order"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["original_song_title"], "晴天")
        self.assertEqual(rows[1]["original_song_title"], "Shape of You")
        self.assertEqual(len(verified_tracks(self.tracks)), 2)

    def test_csv_has_utf8_bom_and_unicode(self):
        csv_bytes = to_csv_bytes(self.tracks)
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
        text = csv_bytes.decode("utf-8-sig")
        self.assertIn("晴天", text)
        self.assertIn("周杰伦", text)
        self.assertIn("youtube_music_video_id", text)
        self.assertNotIn("Unconfirmed", text)

    def test_json_unicode(self):
        payload = json.loads(to_json_bytes(self.tracks).decode("utf-8"))
        self.assertEqual(payload[0]["selected_artist"], "周杰伦")
        self.assertEqual(payload[0]["youtube_music_url"], "https://music.youtube.com/watch?v=vid1")

    def test_duplicates_warn_without_deleting(self):
        self.tracks[3]["selected_video_id"] = "vid1"
        self.tracks[3]["candidates"][0]["video_id"] = "vid1"
        dupes = duplicate_video_ids(self.tracks)
        self.assertEqual(set(dupes["vid1"]), {"1", "4"})
        self.assertEqual(len(verified_tracks(self.tracks)), 2)


class AuthKindTests(unittest.TestCase):
    def test_detect_oauth_and_browser(self):
        self.assertEqual(detect_auth_kind({"access_token": "x", "refresh_token": "y"}), "oauth")
        self.assertEqual(detect_auth_kind({"Cookie": "a=b", "Authorization": "SAPISIDHASH"}), "browser")


if __name__ == "__main__":
    unittest.main()
