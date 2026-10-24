"""Test helpers shared by the API test modules."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

# Fields the public API returns for every song.
SONG_FIELDS = {
    "id", "title", "danceability", "energy", "mood", "acousticness",
    "tempo", "duration_ms", "num_sections", "num_segments", "valence", "rating",
}  # fmt: skip


def make_song(n: int) -> dict:
    """A dataset record (including the internal `sources` field)."""
    return {
        "id": f"id{n:03d}",
        "title": f"Song {n}",
        "danceability": 0.5,
        "energy": None if n % 2 else 0.7,
        "mood": n % 2,
        "acousticness": 0.1,
        "tempo": 120.0,
        "duration_ms": 200_000 + n,
        "num_sections": 8,
        "num_segments": 800,
        "valence": None,
        "sources": ["part1"],
    }


def public(song: dict) -> dict:
    """What the API exposes for an unrated dataset record: no `sources`, `rating` null."""
    return {**{k: v for k, v in song.items() if k != "sources"}, "rating": None}


def write_songs(tmp_path: Path, songs: list[dict]) -> Path:
    path = tmp_path / "songs.json"
    path.write_text(json.dumps(songs))
    return path


def client_with(tmp_path: Path, songs: list[dict], ratings_path: Path | None = None, **kwargs) -> TestClient:
    """A client over `songs`; ratings go to a database inside tmp_path.
    Use as a context manager so the app's startup runs."""
    app = create_app(write_songs(tmp_path, songs), ratings_path or tmp_path / "ratings.db", **kwargs)
    return TestClient(app)


def client_for(tmp_path: Path, count: int) -> TestClient:
    return client_with(tmp_path, [make_song(n) for n in range(count)])


def ids(body: dict) -> list[str]:
    return [s["id"] for s in body["songs"]]
