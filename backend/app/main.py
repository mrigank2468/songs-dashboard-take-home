"""FastAPI entry point.  Run from the backend directory with:

    uvicorn app.main:app
"""

import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.data import DATA_FILE, load_songs
from app.ratings import RATINGS_DB, RatingsStore
from app.schemas import RatingIn, RatingOut, SongPage, SortField, SortOrder
from app.search import filter_by_title
from app.sorting import sort_songs

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

# Origins allowed to call the API from a browser: the Vite dev server of the
# planned local React frontend.  Deliberately not "*".
CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def get_songs(request: Request) -> list[dict[str, Any]]:
    return request.app.state.songs


def get_ratings(request: Request) -> RatingsStore:
    return request.app.state.ratings


def require_song(request: Request, song_id: str) -> str:
    """Path dependency: 404 unless ``song_id`` is a song in the dataset."""
    if song_id not in request.app.state.song_ids:
        raise HTTPException(status_code=404, detail=f"Song not found: {song_id}")
    return song_id


def with_ratings(songs: list[dict[str, Any]], ratings: dict[str, int]) -> list[dict[str, Any]]:
    """Copies of ``songs`` with their rating filled in (None if unrated).
    The stored dataset is never modified."""
    return [{**song, "rating": ratings.get(song["id"])} for song in songs]


def paginate(songs: list[dict[str, Any]], page: int, size: int) -> dict[str, Any]:
    """Slice one page out of the full list.  A page past the end is empty."""
    total = len(songs)
    start = (page - 1) * size
    return {
        "songs": songs[start : start + size],
        "page": page,
        "size": size,
        "total": total,
        "total_pages": math.ceil(total / size),
    }


def create_app(
    data_path: Path = DATA_FILE,
    ratings_path: Path | None = None,
    cors_origins: tuple[str, ...] = CORS_ORIGINS,
) -> FastAPI:
    """Build the app.  The song dataset is loaded once at startup and only read;
    ratings live in their own SQLite file (``ratings_path``)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.songs = load_songs(data_path)
        app.state.song_ids = {song["id"] for song in app.state.songs}
        app.state.ratings = RatingsStore(ratings_path or RATINGS_DB)
        yield

    app = FastAPI(title="Songs API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["GET", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.get("/songs", response_model=SongPage)
    def list_songs(
        songs: list[dict[str, Any]] = Depends(get_songs),
        ratings: RatingsStore = Depends(get_ratings),
        page: int = Query(1, ge=1, description="1-based page number"),
        size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Songs per page"),
        sort_by: SortField | None = Query(
            None, description="Field to sort the whole result set by; omit to keep the dataset's own order"
        ),
        order: SortOrder = Query(SortOrder.asc, description="Sort direction; only used with sort_by"),
        title: str | None = Query(
            None,
            description=(
                "Title substring match, ignoring case, surrounding whitespace and repeated inner whitespace. "
                "Empty or whitespace-only means no filter."
            ),
        ),
    ):
        # Order of operations: filter by title, sort what is left, then take the page.
        # total / total_pages therefore describe the filtered set.
        matches = with_ratings(filter_by_title(songs, title), ratings.all())
        return paginate(sort_songs(matches, sort_by, order), page, size)

    @app.get("/songs/{song_id}/rating", response_model=RatingOut)
    def get_rating(song_id: str = Depends(require_song), ratings: RatingsStore = Depends(get_ratings)):
        return {"song_id": song_id, "rating": ratings.get(song_id)}

    @app.put("/songs/{song_id}/rating", response_model=RatingOut)
    def put_rating(body: RatingIn, song_id: str = Depends(require_song), ratings: RatingsStore = Depends(get_ratings)):
        """Create or replace the rating (1-5) of one song, identified by its id."""
        ratings.set(song_id, body.rating)
        return {"song_id": song_id, "rating": body.rating}

    return app


app = create_app()
