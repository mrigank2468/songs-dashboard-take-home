from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.ratings import MAX_RATING, MIN_RATING


class Song(BaseModel):
    """A normalized song.  Fields the exports could not supply are null.

    The dataset's ``sources`` field is kept for traceability but deliberately
    not exposed: response_model drops keys that are not declared here.
    ``rating`` is not part of the dataset; it is filled in from the ratings
    store and is null until the song has been rated.
    """

    id: str
    title: str | None
    danceability: float | None
    energy: float | None
    mood: int | None
    acousticness: float | None
    tempo: float | None
    duration_ms: int | None
    num_sections: int | None
    num_segments: int | None
    valence: float | None
    rating: int | None = None


class SongPage(BaseModel):
    songs: list[Song]
    page: int
    size: int
    total: int
    total_pages: int


# Sortable fields are exactly the fields the API exposes, so the two cannot drift.
SortField = StrEnum("SortField", {name: name for name in Song.model_fields})


class SortOrder(StrEnum):
    asc = "asc"
    desc = "desc"


class RatingIn(BaseModel):
    """Body of a rating request.  Only a whole number from 1 to 5 is accepted:
    not a string, float or boolean, and no extra keys."""

    model_config = ConfigDict(extra="forbid")

    rating: Annotated[int, Field(strict=True, ge=MIN_RATING, le=MAX_RATING)]


class RatingOut(BaseModel):
    song_id: str
    rating: int | None  # null when the song has not been rated
