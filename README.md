# 🎵 Playlist Assistant

**Turn YouTube music videos into your own playlists.**

Playlist Assistant helps you identify songs from YouTube videos and compile them into a playlist without manually searching for every track. Whether the song list is provided in text, hidden in the video description or comments, or needs to be identified from the audio itself, Playlist Assistant offers multiple methods to extract your favourite songs.

## ✨ Features

- 🎶 **Create YouTube Music Playlists** — Collect identified songs and add them to a YouTube Music playlist.
- 📄 **Export to TXT** — Save extracted song titles and artists to a text file for later use.
- 🔎 **Multiple Song Identification Methods** — Choose the method that best fits your YouTube video.
- 💬 **Extract from Descriptions and Comments** — Find song lists hidden in video descriptions and popular comments.
- 🎧 **Audio Recognition with ShazamIO** — Identify songs directly from audio when song information is not available as text.

## 🚀 How It Works

Playlist Assistant provides three methods for identifying songs.

### Method 1: Extract from a Text List

**Best for:** Videos with an existing song list, timestamps, or a copied list of song titles.

1. Provide a text list containing song titles and, if available, artist names.
2. Let Playlist Assistant process and organize the song information.
3. Review the extracted songs.
4. Add the songs to YouTube Music or export them to a TXT file.

### Method 2: Extract from YouTube Descriptions and Comments

**Best for:** Music compilations where the song list may be included in the description or comments.

1. Provide the YouTube video URL.
2. Retrieve available song information from the video description.
3. Examine relevant comments, including popular comments, for additional song lists and timestamps.
4. Review the extracted results and select the songs you want.
5. Export the selected songs to TXT or create a YouTube Music playlist.

This method helps discover songs even when the uploader has not provided a complete song list in one place.

### Method 3: Identify Songs Using ShazamIO

**Best for:** Videos that do not provide sufficient song information in their descriptions or comments.

1. Provide the YouTube video URL.
2. Playlist Assistant processes the available audio in segments.
3. ShazamIO attempts to recognize the songs using audio fingerprints.
4. Review the recognized song titles and artists.
5. Export the results to TXT or add the songs to YouTube Music.

**Note:** Audio recognition depends on audio quality, song length, background noise, and the recognition service's ability to identify a track. Some songs may not be recognized correctly.

## 🛠️ Available Output Options

| Output                 | Description                                                                                     |
| ---------------------- | ----------------------------------------------------------------------------------------------- |
| YouTube Music Playlist | Collect identified tracks into a playlist for convenient listening.                             |
| TXT File               | Export song titles and artist names into a plain-text file for editing, sharing, or future use. |

## 📋 Example

Given a YouTube music compilation, Playlist Assistant might produce a list like this:

```text
1. Song Title One - Artist A
2. Song Title Two - Artist B
3. Song Title Three - Artist C
```

You can then review the results and choose your preferred output.

## ⚙️ Getting Started

1. Clone this repository.
2. Install the project's dependencies.
3. Configure any required credentials or API tokens.
4. Start the application and provide a YouTube video URL or a song list.
5. Select an extraction method and choose your output format.

Refer to the project's source code and dependency files for the specific installation commands and configuration requirements.

### API Configuration

Some extraction methods may require external services or credentials. If using a method that requires an API token, obtain the token from the relevant provider and enter it when prompted by the application.

For ShazamIO, follow the implementation and dependency requirements in the project.

**Security tip:** Do not commit API tokens, passwords, or other secrets to your Git repository. Store sensitive configuration in environment variables or a local `.env` file and exclude that file from version control.

## ⚠️ Limitations

- Song recognition may be incomplete or inaccurate.
- YouTube descriptions and comments may not contain a complete song list.
- Duplicate tracks or different versions of the same song may require manual review.
- Playlist creation may depend on YouTube Music authentication and track availability.
- Third-party services and platform changes may affect extraction results.

## 🎯 Project Goal

Playlist Assistant aims to make music discovery and playlist creation easier by combining text extraction, YouTube metadata analysis, and audio recognition in one workflow.

**Spend less time identifying songs and more time enjoying the music.** 🎶

## 📄 Disclaimer

This project is intended for personal music discovery and playlist management. Please respect copyright, platform terms of service, and the privacy and usage policies of any third-party services used.
