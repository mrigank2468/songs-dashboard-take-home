# Review of `review/buggy_api.py`

Pull-request-style review of the AI-generated API. **Verdict: request changes.** The file runs, but the
list endpoint returns the wrong songs, ratings are attached to the wrong songs and are lost on restart,
and most invalid or unusual input produces a 500 or a misleading 200. The findings below are ordered by priority.

- **P1:** returns wrong data, loses data, or crashes on realistic input. Block the merge.
- **P2:** robustness, contract or maintainability risk. Fix in this PR or immediately after.

**How this was checked.** I read the code, then ran it unmodified against a copy of the normalized dataset
(25 songs, two titled "Perfect", some null values) using FastAPI's test client. Findings marked *(reproduced)*
were observed. Findings marked *(from the code)* follow directly from the code but were not run. Line
numbers refer to `review/buggy_api.py`. The file was not modified.


---

## P1

### 1. Off-by-one pagination skips the first page
- **Where:** line 35, `start = page * size`.
- **Problem:** pages are 1-based by default (`page: int = 1`), but the slice starts at `page * size`, so page 1 returns songs 10-19 and page 0 returns the first ten.
- **Impact:** the first `size` songs are unreachable from page 1 and the last page comes back empty. *(reproduced: with 25 songs and size 10, page 1 returned items 10-19, page 2 returned 5 items, page 3 returned 0.)*
- **Fix:** `start = (page - 1) * size`, and reject `page < 1` (see 11).

### 2. Sorting happens after slicing, so it is not global
- **Where:** lines 37-39. The page is cut first, then only that page is sorted.
- **Problem:** `sort_by` reorders the ten rows already selected, not the whole dataset.
- **Impact:** "sort by tempo" shows an arbitrary ten songs in tempo order rather than the lowest tempos overall. *(reproduced: the five "lowest" tempos returned were 90, 109, 120, 126, 154; the true five lowest are 77, 90, 90, 93, 95.)*
- **Fix:** sort the whole list first, then slice. Apply any filter before the sort, so the order is filter, sort, paginate.

### 3. Unknown or null sort values crash with a 500
- **Where:** line 39, `key=lambda s: s[sort_by]`; `sort_by` is a free string with a default of `"title"`.
- **Problem:** an unknown field raises `KeyError`; a field with null values (the normalized data has them, e.g. `energy`, `valence`) raises `TypeError` when `None` is compared with a number. Nothing is caught.
- **Impact:** a typo or any column containing a null takes the endpoint down with a 500. *(reproduced: `sort_by=bogus` and `sort_by=energy` both returned 500.)*
- **Fix:** accept only the known fields (an enum or `Literal`, which yields a 422). Use a null-safe key that puts missing values last in both directions and breaks ties by `id`.

### 4. Ratings are keyed by title, so duplicate titles collide
- **Where:** lines 55-62, `ratings[title] = stars` and a loop that sets `song["rating"]` on every match.
- **Problem:** titles are not unique (there are two "Perfect" songs), and the loop does not stop at the first match. A rating for "Perfect" is written to every song with that title, and an unknown title is accepted and stored.
- **Impact:** rating one song silently rates another, and typos pollute the store. *(reproduced: one request set rating 5 on both "Perfect" songs; rating "Nope" returned 200 and left a junk key in `ratings`.)*
- **Fix:** identify songs by their unique `id` (`PUT /songs/{song_id}/rating`) and return 404 when the id does not exist.

### 5. Rating value is never validated
- **Where:** line 56, `stars: int`.
- **Problem:** any integer is accepted. There is no 1-5 range, and the value comes from the query string of a `POST` rather than a request body.
- **Impact:** 0, -5 or 999 are stored as ratings and later shown and averaged. *(reproduced: stars 0, -5 and 999 all returned 200; a JSON body with `stars` got 422 because only the query string is read.)*
- **Fix:** take a JSON body model with `rating: int` constrained to 1-5 (strict, so `"4"`, `4.5` and `true` are rejected), and use `PUT` since setting a rating is idempotent.

### 6. Ratings are not persisted
- **Where:** lines 52 and 57, a module-level `ratings = {}`; line 61 mutates the in-memory cache.
- **Problem:** ratings live only in process memory. Nothing reads the `ratings` dict at all, and the cache that does carry the rating is discarded on restart.
- **Impact:** every restart (or reload, or deploy) erases all ratings, and with multiple workers each process holds different ratings. *(from the code)*
- **Fix:** store ratings in a small persistent store separate from the song data (SQLite is enough, with an upsert per rating), and merge them into responses at read time.

### 7. Data file path is wrong, relative and unvalidated
- **Where:** line 25, `open("songs.json")`, plus lines 26-28.
- **Problem:** the path is relative to the process's working directory, the name does not match the normalized output (`songs_normalized.json`), no encoding is given (`Café` breaks on platforms that do not default to UTF-8), and the file is read lazily on the first request with no validation that it is a list of valid records.
- **Impact:** the service works only when launched from one directory, and a missing or malformed file shows up as a 500 on the first user request, not at startup. *(reproduced: from another directory the first call raised `FileNotFoundError`.)*
- **Fix:** resolve the path from `__file__`, open with `encoding="utf-8"`, and load and validate once at startup (lifespan), failing with a message that names the file and the bad record.

### 8. Title lookup is case-sensitive and hides duplicates
- **Where:** lines 43-49, `GET /songs/{title}` returns the first exact match.
- **Problem:** matching is exact and case-sensitive, returns only the first hit although titles repeat, and puts the title in the URL path (a title containing `/` cannot be addressed).
- **Impact:** a search for "perfect" finds nothing, and "Perfect" silently returns one of two different songs. *(reproduced: `/songs/perfect` returned not found; `/songs/Perfect` returned one song of the two.)*
- **Fix:** make title search a query parameter on the list endpoint (`GET /songs?title=...`) that normalizes case and whitespace and returns every match with correct paging totals.

### 9. Failures return 200, or an unhandled 500
- **Where:** line 49 (`return {"error": "not found"}`), line 62 (rating an unknown title), and the unhandled exceptions from 3 and 13.
- **Problem:** not-found is reported with HTTP 200 and an error body, rating a missing song succeeds, and bad input surfaces as a bare 500.
- **Impact:** clients, retries and monitoring cannot tell success from failure. *(reproduced: unknown title lookup returned 200 `{"error": "not found"}`; rating an unknown title returned 200.)*
- **Fix:** raise `HTTPException(404, ...)` for missing songs, rely on validation for 422, and keep 500 for real server faults.

## P2

### 10. Rating mutates the shared cached records
- **Where:** line 61, `song["rating"] = stars` on the cached dicts that every request reads.
- **Problem:** a write request edits shared, unlocked state, and the `rating` key exists only on songs that were rated.
- **Impact:** concurrent requests race on the same dicts, and responses have an inconsistent shape. *(reproduced: Africa gained a `rating` key after being rated; other songs had none.)*
- **Fix:** treat the loaded dataset as read-only and build response copies with `rating` always present (null when unrated).

### 11. Paging and ordering parameters are unbounded or unchecked
- **Where:** line 33, `page: int = 1, size: int = 10, order: str = "asc"`.
- **Problem:** `page` and `size` accept zero and negative values and have no upper limit, and `order` treats anything other than `"desc"` as ascending. Ties have no defined order, so repeated requests may differ.
- **Impact:** negative values give meaningless slices (e.g. `size=-3` at page 0 is `songs[0:-3]`), `size=100000` returns the whole dataset, and `order=banana` is silently accepted. *(reproduced: `size=0` returned an empty page, `order=banana` returned 200.)*
- **Fix:** `page >= 1`, `1 <= size <= 100`, `order` restricted to `asc`/`desc`, and a deterministic tie-break (for example by `id`).

### 12. Mutable-default cache: first-load race and global state
- **Where:** lines 21-29, `load_songs(_cache=[])`, `if _cache:`.
- **Problem:** the cache is a mutable default argument shared by every call. Two requests arriving before it is filled both load the file and both append. An empty dataset is treated as "not loaded" and is re-read on every call. The module-level globals (`_cache`, `ratings`, the relative path) also make the code hard to test.
- **Impact:** concurrent first requests can duplicate every song for the life of the process. *(reproduced: four simultaneous first loads left 100 rows from a 25-song file.)*
- **Fix:** load once at startup (lifespan or a locked loader), keep the data on `app.state`, and inject it into the routes so tests can supply their own.

### 13. Duration statistics crash on empty or null data
- **Where:** lines 65-72, `/stats/duration`.
- **Problem:** `total / len(songs)` divides by zero for an empty dataset, `s["duration_ms"] / 1000` raises `TypeError` for a null duration (the normalizer nulls durations it cannot trust), and the response gives no count of the songs used.
- **Impact:** one empty file or one null duration turns the endpoint into a 500. *(from the code; the current 25-song data has no null durations, and the endpoint returned 251.99 s.)*
- **Fix:** average only non-null durations, return `null` with a count when none exist, and add a test with nulls.

### 14. Response contract is accidental and leaks `sources`
- **Where:** line 40 (returns `items`) and lines 48/62 (return raw records).
- **Problem:** there is no response model, so each record is returned exactly as stored, including the internal `sources` traceability field. The list response has no `total_pages`, and the name `items` is undocumented in the schema.
- **Impact:** internal fields leak to clients, the schema in `/docs` is empty, and the frontend must compute page counts itself. *(reproduced: a song response contained `sources`, and the list had no `total_pages`.)*
- **Fix:** declare Pydantic response models for songs and pages (with `total_pages`), and expose only the intended fields.

### 15. No CORS configuration for the React frontend
- **Where:** line 18, `FastAPI()` with no middleware.
- **Problem:** a browser app served from another origin (the Vite dev server) is blocked from calling the API.
- **Impact:** the dashboard cannot load data in the browser even though `curl` works. *(from the code.)*
- **Fix:** add `CORSMiddleware` allowing only the frontend's origins and the methods the API uses, not `*`.

---

## How the submitted backend addresses these

| # | In `backend/` |
|---|---|
| 1, 2 | `paginate` uses `(page - 1) * size`; the route filters, sorts the whole result, then paginates. |
| 3, 11 | Sort field and order are enums (422 otherwise); nulls sort last in both directions; ties break by `id`; `page >= 1`, `size` 1-100. |
| 4, 5, 9 | Ratings use song ids and a strict 1-5 integer body; unknown ids return 404 and invalid bodies 422. |
| 6, 10 | Ratings are stored in SQLite, separate from the dataset; the stored songs are never modified. |
| 7, 12 | The data path is resolved from the module, and the file is validated once at startup. |
| 8 | Title search is a `title` query parameter on `GET /songs`: case, outer whitespace and whitespace runs are ignored and all matches are returned (exact match, not substring). |
| 13 | Not implemented: the submitted backend has no `/stats/duration` endpoint. |
| 14, 15 | `SongPage` is the response model and hides `sources`; CORS is limited to `localhost:5173` and `127.0.0.1:5173`. |

### PR Review Judgment

**PR blockers — P1 (#1–#9):** I would block the PR on these issues because they affect core API correctness, data integrity, validation, persistence, reliable data loading, or error handling. Pagination must return the correct page, sorting must apply globally before pagination, ratings must identify songs uniquely and validate values, and invalid requests must produce appropriate responses.

**Non-blocking follow-ups — P2 (#10–#15):** These issues should be tracked and addressed based on risk and deployment needs. They cover shared-state mutation, unchecked parameters, cache safety, duration-statistics edge cases, response-contract quality, and CORS configuration. Some, especially cache safety and input validation, should be fixed before production. CORS is relevant when the frontend and backend run on different origins.

**Nits:** None of the 15 findings is merely a stylistic nit; each identifies a functional, reliability, contract, or integration concern.

My prioritization puts correctness and data integrity first. P2 means non-blocking for this review, not necessarily safe to leave unfixed in production.