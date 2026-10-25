"""Title search over the full song list.  Pure; the input list is never modified."""

from typing import Any

from app.normalizer import title_key


def filter_by_title(songs: list[dict[str, Any]], title: str | None) -> list[dict[str, Any]]:
    """Songs whose title contains ``title`` after normalization.

    Titles are compared with ``title_key`` (Unicode-normalized, case-insensitive,
    whitespace runs collapsed, ends trimmed), the same key used to spot duplicate
    titles during normalization.  It is a substring match, so partial text finds
    songs, and returns every match since titles are not unique.  A missing, empty or
    whitespace-only ``title`` means "no filter", and songs without a title never
    match a real search.
    """
    wanted = title_key(title) if title is not None else ""
    if not wanted:
        return songs
    return [s for s in songs if s.get("title") is not None and wanted in title_key(s["title"])]
