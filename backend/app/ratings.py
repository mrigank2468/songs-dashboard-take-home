"""Persistent star ratings, stored in SQLite and kept apart from the song data.

SQLite is in the standard library, writes are atomic, and an upsert touches only
one row, so rating one song can never drop another song's rating, even with
concurrent requests or several server processes.  Every operation opens its own
short-lived connection, which keeps the store safe to share between the threads
FastAPI runs sync endpoints on.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

# Runtime state, not source data (``*.db`` is gitignored).
RATINGS_DB = Path(__file__).resolve().parent.parent / "data" / "ratings.db"

MIN_RATING = 1
MAX_RATING = 5

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS ratings (
    song_id TEXT PRIMARY KEY,
    rating  INTEGER NOT NULL CHECK (rating BETWEEN {MIN_RATING} AND {MAX_RATING})
)
"""


class RatingsStore:
    def __init__(self, path: Path = RATINGS_DB):
        self.path = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn, conn:
                conn.execute(_SCHEMA)
        except (sqlite3.Error, OSError) as e:
            raise RuntimeError(f"Cannot open ratings database {path}: {e}") from e

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)  # wait, don't fail, on a locked file

    def all(self) -> dict[str, int]:
        with closing(self._connect()) as conn:
            return dict(conn.execute("SELECT song_id, rating FROM ratings"))

    def get(self, song_id: str) -> int | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT rating FROM ratings WHERE song_id = ?", (song_id,)).fetchone()
        return row[0] if row else None

    def set(self, song_id: str, rating: int) -> None:
        """Create or replace one song's rating (a single atomic statement)."""
        with closing(self._connect()) as conn, conn:  # `with conn` commits or rolls back
            conn.execute(
                "INSERT INTO ratings (song_id, rating) VALUES (?, ?) "
                "ON CONFLICT(song_id) DO UPDATE SET rating = excluded.rating",
                (song_id, rating),
            )
