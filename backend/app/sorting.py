"""Sort the full song list.  Pure functions: the input list is never modified."""

from typing import Any, Callable

# Per-field comparison keys.  Anything not listed compares by its own value.
# Titles ignore case; ids are case-sensitive, so they are left alone.
_SORT_KEYS: dict[str, Callable[[Any], Any]] = {"title": str.casefold}


def sort_songs(songs: list[dict[str, Any]], field: str | None, order: str = "asc") -> list[dict[str, Any]]:
    """Return ``songs`` sorted by ``field``; with no field, in the original order.

    * Songs whose value is null (or absent) always come last, in both
      directions, so "descending" does not push missing data to the top.
    * Ties are broken by ``id`` ascending in both directions, so the result
      does not depend on the order of the input or on the direction.
    """
    if field is None:
        return songs
    key = _SORT_KEYS.get(field, lambda value: value)
    by_id = sorted(songs, key=lambda song: song["id"])
    present = [song for song in by_id if song.get(field) is not None]
    missing = [song for song in by_id if song.get(field) is None]
    # list.sort keeps equal elements in their existing (id) order even with
    # reverse=True, which is what makes the id tie-break hold for "desc".
    present.sort(key=lambda song: key(song[field]), reverse=(order == "desc"))
    return present + missing
