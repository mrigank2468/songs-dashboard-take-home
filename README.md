# Songs dashboard take-home

A FastAPI backend that serves a cleaned song catalog with pagination, global sorting,
title search and persistent star ratings. The React frontend (`frontend/`) has not been started.

The catalog comes from two inconsistent exports (`backend/data/songs_part1.json`,
`songs_part2.json`). A normalizer merges them into `backend/data/songs_normalized.json`
and writes a report of every change to `backend/data/data_quality_report.json`.
The design decisions are in [DECISIONS.md](DECISIONS.md).

## Layout

```
backend/
  app/
    main.py         FastAPI app and routes (entry point: app.main:app)
    data.py         loads and validates songs_normalized.json
    schemas.py      response / request models
    search.py       title filter
    sorting.py      global sort (nulls last, deterministic ties)
    ratings.py      SQLite-backed ratings store
    normalizer.py   merges and cleans the two exports
  data/             source exports, normalized dataset, quality report (ratings.db appears here at runtime)
  tests/
  requirements.txt  fastapi, uvicorn, pytest, httpx
```

## Setup

All commands run from `backend/`. The virtual environment is `backend/.venv` (Python 3.13).

```bash
cd backend
source .venv/bin/activate          # or call .venv/bin/python directly
```

To recreate it from scratch:

```bash
cd backend
uv venv --python 3.13 --managed-python
uv pip install --python .venv/bin/python -r requirements.txt
```

`--managed-python` makes uv download its own CPython. Homebrew's Python 3.13.17 on the
development machine had a `pyexpat` that did not match macOS's system `libexpat`, which
broke `venv`/`ensurepip`; uv's build bundles its own expat. If your Python works, plain
`python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt` is fine.

## Run the API

```bash
cd backend
uvicorn app.main:app --reload      # http://127.0.0.1:8000, interactive docs at /docs
```

The app loads `data/songs_normalized.json` from its own location, so the working directory does not
matter for the data file (the `app.main:app` import path does need `backend/` as the working directory,
or `--app-dir backend`). A missing or invalid data file stops startup with an error naming the file.

## Run the tests

```bash
cd backend
python -m pytest                   # the whole suite
```

Tests never touch `data/ratings.db`; a session fixture fails the run if they do.
Rebuild the normalized data (not needed normally, the output is committed):
`python -m app.normalizer`.

## API

### `GET /songs`

| Parameter | Default | Rules |
|---|---|---|
| `page` | 1 | integer >= 1 |
| `size` | 10 | integer 1-100 |
| `sort_by` | none (dataset order) | `id`, `title`, `danceability`, `energy`, `mood`, `acousticness`, `tempo`, `duration_ms`, `num_sections`, `num_segments`, `valence`, `rating` |
| `order` | `asc` | `asc` or `desc`; ignored without `sort_by` |
| `title` | none | exact title match, ignoring case, outer whitespace and repeated inner whitespace; empty or blank means no filter |

Order of operations: filter by title, sort the whole result, then take the page.
`total` and `total_pages` describe the filtered set. Songs with a null value for the sort field come
last in both directions; ties are ordered by `id` ascending. A page past the end returns an empty list (200).

```bash
curl 'localhost:8000/songs'                                  # page 1, 10 songs
curl 'localhost:8000/songs?page=2&size=5'
curl 'localhost:8000/songs?sort_by=tempo&order=desc'
curl 'localhost:8000/songs?title=%20perfect%20&sort_by=duration_ms&order=desc'
curl 'localhost:8000/songs?sort_by=rating&order=desc&size=4'
```

```json
{
  "songs": [
    {"id": "0tgVpDi06FyKpA1z0VMD4v", "title": "Perfect", "danceability": 0.599, "energy": 0.448,
     "mood": 1, "acousticness": 0.163, "tempo": 95.05, "duration_ms": 263400, "num_sections": 9,
     "num_segments": 940, "valence": 0.61, "rating": 3}
  ],
  "page": 1, "size": 10, "total": 2, "total_pages": 1
}
```

(Abridged: the `title=perfect` query returns both "Perfect" songs, so `total` is 2.)

Unavailable values are `null`. `rating` is `null` until the song is rated. The internal `sources`
field is not exposed. Invalid parameters return `422` with FastAPI's error list, e.g.
`{"detail": [{"loc": ["query", "size"], "msg": "Input should be less than or equal to 100", ...}]}`.

### `PUT /songs/{song_id}/rating`

Creates or replaces a rating. The song is identified by its `id`, not its title.

```bash
curl -X PUT localhost:8000/songs/7fBv7CLKzipRk6EC6TWHOB/rating \
     -H 'content-type: application/json' -d '{"rating": 5}'
# {"song_id": "7fBv7CLKzipRk6EC6TWHOB", "rating": 5}
```

| Case | Response |
|---|---|
| `rating` is an integer 1-5 | `200` |
| `rating` is 0, 6, a float, a string, a boolean, null, missing, or the body has extra keys / is not JSON | `422` |
| unknown `song_id` (checked first, whatever the body) | `404` `{"detail": "Song not found: <id>"}` |

### `GET /songs/{song_id}/rating`

`{"song_id": "...", "rating": 5}`, or `"rating": null` if unrated. `404` for an unknown song.

### CORS

Browsers on `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite dev server) may call the API.
Other origins get no CORS headers. Change `CORS_ORIGINS` in `app/main.py` if the frontend uses another port.

## Ratings storage

Ratings live in a SQLite file, `backend/data/ratings.db` (gitignored, created on first start), separate
from the song data. They survive restarts. See [DECISIONS.md](DECISIONS.md) for the reasoning and limits.
