"""Parse pasted song lists into title/singer rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ParsedLine:
    line_number: int
    raw: str
    title: str | None
    singer: str | None
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _split_song_and_singer(text: str) -> tuple[str, str] | None:
    """Split a single line into song title and singer.

    Preferred delimiters, in order:
    1. Tab
    2. ASCII comma or fullwidth comma
    3. Space-hyphen-space (including en/em dashes)
    """
    if "\t" in text:
        left, right = text.split("\t", 1)
        return left.strip(), right.strip()

    for comma in (",", "，"):
        if comma in text:
            left, right = text.split(comma, 1)
            return left.strip(), right.strip()

    for dash in (" - ", " – ", " — "):
        if dash in text:
            left, right = text.split(dash, 1)
            return left.strip(), right.strip()

    return None


def parse_song_list(text: str) -> tuple[list[ParsedLine], list[ParsedLine]]:
    """Parse multiline input.

    Returns (valid_entries, malformed_entries). Blank lines and lines
    starting with ``#`` are ignored. Original title, singer, raw text,
    and line number are preserved. Duplicate titles/singers are allowed.
    """
    valid: list[ParsedLine] = []
    malformed: list[ParsedLine] = []

    if text is None:
        return valid, malformed

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        raw = raw_line.strip()
        if not raw or raw.startswith("#"):
            continue

        parts = _split_song_and_singer(raw)
        if parts is None:
            malformed.append(
                ParsedLine(
                    line_number=line_number,
                    raw=raw_line,
                    title=None,
                    singer=None,
                    error="No recognized delimiter. Use 'Song, Singer', 'Song - Singer', or Song<TAB>Singer.",
                )
            )
            continue

        title, singer = parts
        if not title or not singer:
            malformed.append(
                ParsedLine(
                    line_number=line_number,
                    raw=raw_line,
                    title=title or None,
                    singer=singer or None,
                    error="Song title and singer are both required.",
                )
            )
            continue

        valid.append(
            ParsedLine(
                line_number=line_number,
                raw=raw_line,
                title=title,
                singer=singer,
                error=None,
            )
        )

    return valid, malformed
