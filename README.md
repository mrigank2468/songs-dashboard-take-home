# Songs dashboard take-home

A FastAPI backend that serves a cleaned song catalog with pagination, global sorting,
title search and persistent star ratings, and a React dashboard (`frontend/`) for browsing,
searching, sorting, rating and exporting the songs.

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
frontend/           React + TypeScript + Vite + MUI dashboard
  src/api.ts        API types and calls (the only code that talks to the backend)
  src/App.tsx       state and data loading; SongTable.tsx, RatingSelect.tsx are the UI pieces
  src/csv.ts        CSV building and download
```

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ (developed and tested on 3.13) | the code uses `StrEnum`, added in 3.11 |
| [uv](https://docs.astral.sh/uv/) | any recent | optional; used below to create the environment. Plain `python -m venv` also works |
| Node.js + npm | 20+ (built with Node 22) | frontend only |

The backend (port 8000) and the frontend (port 5173) are separate processes, so use two terminals.

## Backend setup

Run from `backend/`. The environment lives in `backend/.venv` (gitignored).

**With uv (macOS, Linux, Windows):**

```bash
cd backend
uv venv --python 3.13
uv pip install -r requirements.txt
```

`uv pip` installs into `.venv` automatically. If you have a working Python, `uv venv` without
`--python` uses it. If a system Python is broken (the development machine's Homebrew Python 3.13
had a `pyexpat` that did not match macOS's `libexpat`, which broke `venv`/`ensurepip`), add
`--managed-python` so uv downloads its own CPython.

**Without uv:**

| | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| create | `python3 -m venv .venv` | `py -m venv .venv` |
| install | `.venv/bin/pip install -r requirements.txt` | `.venv\Scripts\pip install -r requirements.txt` |

**Activating** is optional; every command below can also call the venv's Python directly
(`.venv/bin/python` on macOS/Linux, `.venv\Scripts\python` on Windows).

| macOS / Linux | Windows PowerShell | Windows cmd |
|---|---|---|
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` | `.venv\Scripts\activate.bat` |

`requirements.txt` lists `fastapi`, `uvicorn`, `pytest` and `httpx` (unpinned).

## Run the API

```bash
cd backend
uvicorn app.main:app --reload      # http://127.0.0.1:8000, interactive docs at /docs
```

(With the environment not activated, use `.venv/bin/python -m uvicorn ...` or
`.venv\Scripts\python -m uvicorn ...`.)

`app.main:app` must be imported from `backend/`, so run the command there (or pass `--app-dir backend`).
The data file and the ratings database are located relative to the code, so the working directory
does not matter for them. A missing or invalid data file stops startup with an error naming the file.
The backend reads no environment variables.

## Run the dashboard

Start the API first, then in a second terminal:

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

| Command (in `frontend/`) | Purpose |
|---|---|
| `npm run dev` | dev server on port 5173 (fails if the port is taken, see CORS) |
| `npm run build` | type-check and build into `dist/` |
| `npm test` | run the frontend tests once (`npm run test:watch` to watch) |
| `npm run lint` | lint |

**Configuration:** `VITE_API_BASE_URL` is the backend address; it defaults to `http://localhost:8000`,
so no `.env` file is needed when the API runs on port 8000. To change it, copy `frontend/.env.example`
to `frontend/.env` (`cp .env.example .env` on macOS/Linux, `copy .env.example .env` on Windows cmd,
`Copy-Item .env.example .env` in PowerShell) and edit it. Vite reads it at start-up, so restart the dev
server after changing it.

## Run the tests

```bash
cd backend && python -m pytest     # backend suite (venv active, or use the venv's python)
cd frontend && npm test            # frontend suite
```

Tests never touch `data/ratings.db`; a session fixture fails the run if they do.
To rebuild the normalized data (not needed normally, the output is committed), run
`python -m app.normalizer` from `backend/`.

## Features

- Songs table, 10 per page, with loading, error (with Retry) and empty-result states and
  "1-10 of 25 · page 1 of 3" pagination.
- Columns: title, tempo, danceability, energy, mood, duration (m:ss), valence, rating. Missing values show "—".
  The song id is used for API calls but is not displayed.
- Sorting from the column headers (MUI `TableSortLabel`): the first click sorts ascending, repeated clicks toggle.
  Sorting is done by the server on the whole dataset before paging, and always returns to page 1.
- Title search, debounced by 300 ms, returns to page 1. It uses the backend's rule: part of a title, ignoring case,
  outer whitespace and repeated inner spaces, so every song containing that text is shown. A blank box means no filter.
  Superseded requests are cancelled and a late response can never replace a newer one.
- Rating dropdown per song (Unrated, 1-5), saved with `PUT /songs/{id}/rating`. The control is disabled while saving,
  shows the new value only once the server confirms, and shows an error message if saving fails.
- "Export this page (CSV)" downloads `songs.csv` with the songs currently shown, in the order shown.
  Columns are the displayed ones, headed by their API field names (`title,tempo,danceability,energy,mood,duration_ms,valence,rating`).
  Values are the raw API values (duration in milliseconds, not rounded), missing values are empty fields,
  fields with commas, quotes or line breaks are quoted per RFC 4180, and the file starts with a UTF-8 BOM so Excel reads accented titles correctly.

## Known limitations

- Ratings are global: there are no users, so one rating per song is shared by everyone, and the last
  `PUT` wins. Nothing is averaged.
- A rating cannot be removed: the API has no delete, so "Unrated" is shown for unrated songs but is disabled once a song is rated.
- "Mood" is shown as the raw 0/1 from the data; the data does not say what the values mean.
- The CSV covers the current page only, as requested, and does not guard against spreadsheet formula injection
  (a title starting with `=`, `+`, `-` or `@`).
- Frontend automated tests use a mocked API (src/test/fakeApi.ts). The full application was also manually verified with the real backend.
- CORS allows only the two Vite dev-server origins and is not configurable without editing code (see CORS).

## API

### `GET /songs`

| Parameter | Default | Rules |
|---|---|---|
| `page` | 1 | integer >= 1 |
| `size` | 10 | integer 1-100 |
| `sort_by` | none (dataset order) | `id`, `title`, `danceability`, `energy`, `mood`, `acousticness`, `tempo`, `duration_ms`, `num_sections`, `num_segments`, `valence`, `rating` |
| `order` | `asc` | `asc` or `desc`; ignored without `sort_by` |
| `title` | none | title substring match, ignoring case, outer whitespace and repeated inner whitespace; empty or blank means no filter |

Order of operations: filter by title, sort the whole result, then take the page.
`total` and `total_pages` describe the filtered set. Songs with a null value for the sort field come
last in both directions; ties are ordered by `id` ascending. A page past the end returns an empty list (200).

The examples use `curl` with single quotes (macOS, Linux, Git Bash). On Windows use `curl.exe` (in PowerShell,
`curl` is an alias of `Invoke-WebRequest`) with double quotes, or open the same URLs in a browser.

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

Windows PowerShell:

```powershell
Invoke-RestMethod -Method Put -Uri http://localhost:8000/songs/7fBv7CLKzipRk6EC6TWHOB/rating `
  -ContentType 'application/json' -Body '{"rating": 5}'
```

| Case | Response |
|---|---|
| `rating` is an integer 1-5 | `200` |
| `rating` is 0, 6, a float, a string, a boolean, null, missing, or the body has extra keys / is not JSON | `422` |
| unknown `song_id` (checked first, whatever the body) | `404` `{"detail": "Song not found: <id>"}` |

### `GET /songs/{song_id}/rating`

`{"song_id": "...", "rating": 5}`, or `"rating": null` if unrated. `404` for an unknown song.

### CORS

Only browsers on `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite dev server) may call the API,
and only with `GET` and `PUT` and the `Content-Type` header. Other origins get no CORS headers.
This is the `CORS_ORIGINS` constant in `backend/app/main.py`; edit it (and `server.port` in
`frontend/vite.config.ts`) to serve the frontend from another origin. `curl` and other non-browser
clients are not affected by CORS.

## Ratings storage

Ratings live in a SQLite file, `backend/data/ratings.db` (gitignored, created on first start), separate
from the song data. They survive restarts. See [DECISIONS.md](DECISIONS.md) for the reasoning and limits.
