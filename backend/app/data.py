"""Load the normalized song dataset.

Kept apart from the API so it can be tested, and pointed at other files, on its own.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas import Song

# Resolved from this file, not the working directory, so it works from anywhere.
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "songs_normalized.json"


def load_songs(path: Path = DATA_FILE) -> list[dict[str, Any]]:
    """Read and validate the normalized dataset: a JSON array of song objects.

    Songs keep file order.  Anything wrong with the file (missing, not JSON,
    not an array, a record that is not a valid song, a repeated id) raises with
    the path and the offending record, so the app stops at startup instead of
    failing on a later request.  The file is only ever read.
    """
    try:
        with path.open(encoding="utf-8") as f:
            songs = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(songs, list):
        raise ValueError(f"{path} must contain a JSON array of song objects")

    seen: set[str] = set()
    for index, song in enumerate(songs):
        if not isinstance(song, dict):
            raise ValueError(f"{path}: item {index} is not a song object")
        try:
            Song.model_validate(song)
        except ValidationError as e:
            first = e.errors()[0]
            raise ValueError(
                f"{path}: item {index} is not a valid song ({'.'.join(map(str, first['loc']))}: {first['msg']})"
            ) from e
        if song["id"] in seen:
            raise ValueError(f"{path}: item {index} repeats id {song['id']!r}")
        seen.add(song["id"])
    return songs
