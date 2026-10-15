# Text-to-YouTube-Music Playlist Assistant

Version 1 Python app: paste a list of songs, search **YouTube Music** live, confirm the correct recording for each line, then export CSV/JSON. Optionally create a playlist in a YouTube Music account through **ytmusicapi** (unofficial).

This project is not affiliated with, supported by, or endorsed by Google or YouTube.

## What Version 1 does

1. **Input** — paste `Song, Singer`, `Song - Singer`, or `Song<TAB>Singer` (Unicode / Chinese included).
2. **Search** — live `ytmusicapi` queries (unauthenticated). Up to five candidates per song.
3. **Verification** — you pick and confirm a recording. Nothing is accepted automatically.
4. **Playlist** — reorder, exclude, and review possible duplicates (warnings only).
5. **Export or create** — download CSV/JSON without signing in. Playlist creation is optional and unofficial.

Out of scope: audio recognition, video download, Spotify, auto-accepting search hits, accounts/databases.

## Requirements

- **Python 3.12 or 3.13** (3.13 is preferred). Do not assume Python 3.15 has wheels for every dependency.
- Internet access for YouTube Music search (and for optional playlist creation).

## Setup (macOS)

```bash
cd /path/to/playlist-assistant
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `python3.13` is not installed, `python3.12` is fine:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run:

```bash
streamlit run app.py
```

The app opens in your browser (usually http://localhost:8501).

## Setup (Windows)

In PowerShell:

```powershell
cd \path\to\playlist-assistant
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If execution policy blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again. Python 3.12: `py -3.12 -m venv .venv`.

Command Prompt:

```cmd
.venv\Scripts\activate.bat
pip install -r requirements.txt
streamlit run app.py
```

## Using the app

1. Paste a list. Lines starting with `#` and blank lines are ignored.
2. Click **Parse song list**. Malformed lines are listed; valid lines are kept. Edit the box and parse again whenever you need.
3. Click **Search YouTube Music for all parsed songs**. Progress is shown for the batch.
4. Open each song, compare title / artist / album / duration, open the YouTube Music link if needed, select a candidate, and tick **Confirm this recording**.
5. If none of the results is right, change the title/singer on that row and click **Search again**. Leave the song unconfirmed if you still have no match.
6. In **Playlist**, use ↑ / ↓ to reorder and **Include** to drop a confirmed track without losing the rest of your work.
7. Download **CSV** (UTF-8 with BOM, Excel-friendly) or **JSON**. Only confirmed, included tracks are exported, in your order.

Selections persist across Streamlit reruns. Confirming one song does not clear another.

## Optional YouTube Music playlist creation (unofficial)

`ytmusicapi` is **not** an official Google YouTube Music playlist API. Requests emulate the website. Google can change endpoints at any time. Search and export work **without** authentication; playlist creation needs a local auth file.

**Treat `browser.json` / `oauth.json` as passwords.** Do not share them, screenshot them, or commit them. This repo’s `.gitignore` excludes typical auth filenames.

Follow the current docs, not stale blog posts: https://ytmusicapi.readthedocs.io/

### Browser headers (`browser.json`)

1. Install the project dependencies (so the `ytmusicapi` CLI is available).
2. In a browser, open https://music.youtube.com and stay logged in.
3. Open developer tools → Network. Trigger an authenticated POST to `browse`.
4. Copy the request headers as described in [Browser authentication](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html).
5. Run `ytmusicapi browser` in a terminal and paste the headers (on macOS Terminal, header paste length is limited; see the docs for `pbpaste`).
6. In the app, upload the generated JSON. Choose title, description, and privacy (`PRIVATE`, `UNLISTED`, or `PUBLIC` as supported by the library). Submit **only** after you have confirmed tracks.

### OAuth (`oauth.json`)

As of November 2024, OAuth also needs a Google Cloud **OAuth client ID and secret** (application type: TVs and Limited Input devices). See [OAuth authentication](https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html).

```bash
ytmusicapi oauth
```

Upload `oauth.json` and enter the client ID and secret in the app. Those values are not stored in this project.

If creation succeeds, the app shows a YouTube Music playlist link. If the library returns an error dict instead of an ID, no success message is shown.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `pip` fails to build wheels | Use Python **3.12 or 3.13**, not 3.15. Upgrade pip: `python -m pip install --upgrade pip`. |
| `ModuleNotFoundError: ytmusicapi` / `streamlit` | Activate the virtual environment, then `pip install -r requirements.txt`. |
| Search returns nothing | Edit the title/singer and search that row again. Some songs are missing from YouTube Music. |
| Connection / timeout errors | Check the network. Retry; YouTube may throttle bursts of searches. |
| `Please provide authentication before using this function` | Search should not need auth. Playlist creation does. Upload a current auth file. |
| Auth / 401 / expired session | Generate a new `browser.json` or `oauth.json`. Logging out of YouTube in the browser invalidates browser headers. |
| OAuth setup errors | Confirm the Cloud client is “TVs and Limited Input devices” and pass both client ID and secret. |
| CSV garbled in Excel | The file is UTF-8 with BOM. Open via Data → From Text/CSV and choose UTF-8 if needed. |
| Streamlit widget state looks stale | Parse again after large edits, or refresh the page. Confirmed tracks are stored in session state for the current session only. |

## Project layout

```text
playlist-assistant/
├── app.py                 # Streamlit UI
├── parser.py              # Song-list parsing
├── search.py              # Live YouTube Music search + candidate formatting
├── export.py              # CSV/JSON export
├── playlist_create.py     # Optional unofficial playlist creation
├── requirements.txt
├── README.md
├── .gitignore
└── tests/
    └── test_parser_and_export.py
```

## Tests actually run vs live integrations

**Automated (no YouTube account):**

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py parser.py search.py export.py playlist_create.py
```

These cover parsing (including malformed lines and Unicode), candidate formatting (no invented metadata), mocked search, duplicate warnings without deletion, and CSV/JSON export (UTF-8, confirmed/included only).

**Live YouTube Music search** needs the network and YouTube’s current responses. Run the Streamlit app and search a short list. Results can change.

**Authenticated playlist creation** is not executed in automated tests (it would need your session file). Create a private playlist only after you have a local auth file.

## License / API notice

Use of YouTube Music is subject to Google’s terms. This tool is for personal workflow convenience. Playlist creation may break without notice because it depends on unofficial client behavior.
# playlist_assistant
