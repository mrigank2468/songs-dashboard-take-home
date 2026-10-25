# Decisions

How each decision came about is marked, so a reviewer can tell them apart:
**[requested]** the requirement or instruction came from the prompt, **[AI choice]** the AI picked it
where the prompt was silent (flagged for review, not necessarily confirmed), **[agreed]** proposed by
the AI and then confirmed by a later instruction. Prompt history is in [PROMPTS.md](PROMPTS.md).

## Data normalization

Inputs: `songs_part1.json` (16 rows) and `songs_part2.json` (13 rows), column-oriented JSON
(`{column: {row_index: value}}`). Output: 25 unique songs in `songs_normalized.json` plus
`data_quality_report.json`. Source files are never modified.

- **Merge key is `id`. [requested]** Four ids appear in both files. Songs with the same title but
  different ids are kept as separate records: there are two distinct "Perfect" songs
  (`0tgVpDi06FyKpA1z0VMD4v`, `7dNsHhGeGU5MV01r06O8gK`). The audit could not tell whether they are two releases
  or one song exported twice; the report lists them under `duplicate_titles`.
- **Conflicts: part 1 wins, and the disagreement is reported. [requested]** The only real conflict is
  *Never Gonna Give You Up* `danceability` (0.727 in part 1, 0.74 in part 2). The data cannot say which is
  right; part 1 is kept as a deterministic rule, not a claim that it is more accurate. The report holds both
  original values.
- **Fallback to the other file when the winning value is unusable. [AI choice]** If part 1's value is
  missing or invalid and part 2 has a valid one, part 2's is used and logged under `filled_from_other_source`
  with the original invalid value and the reason. A valid part 1 value is never overridden. In the current
  data this only supplies `valence` (part 1 has no such column) for the four shared songs. No real row has an
  invalid part 1 value with a valid part 2 value, so that path is covered by tests only.
- **Missing values become `null`. [requested]** A missing key, `null`, empty or blank string, and
  `"N/A"`/`na`/`null`/`none`/`nan` (any case) all mean null. `valence` exists only in part 2, so it is null for
  the 12 songs not in part 2.
- **Invalid values become `null` with a recorded reason, never clamped. [requested]** `danceability`,
  `energy`, `acousticness`, `valence` must be in [0, 1]; `tempo` must be above 0 and at most 400; `mood`
  must be 0 or 1; section and segment counts must be positive integers. Affected today: 21 Guns
  `danceability` 1.42, Another Brick `acousticness` -0.05, Blinding Lights `tempo` 0.
- **Numeric strings are converted. [requested]** Only plain decimals (`"108.73"`) are accepted. `"1_0"`,
  `"1e2"`, `"inf"`, non-ASCII digits are invalid. (Python's `float()` alone accepts them; this was tightened
  after review.)
- **`duration_ms` seconds rule. [requested; the corroboration check is an AI choice]** Three part 2 values
  (Sunflower 158, Uptown Funk 270, Sweet Child O Mine 356) were seconds. A value is multiplied by 1000 only
  if it is under 1000 *and* the result is 30 s to 30 min *and* it implies 100-600 ms per segment (the other rows
  sit at about 207-342). A suspicious value that fails the checks becomes null, not a guess. Every correction
  records original, corrected value and reason. Limitation: seconds values of 1000 or more would not be caught.
- **Titles: trim only. [requested]** `" 4 walls  "` becomes `"4 walls"`. Titles that look truncated
  ("Another Brick", "Sweet Child O Mine") are left as they are.
- **Duplicate-title detection ignores case, Unicode form and whitespace runs. [requested after review]**
  Diacritics are not folded ("Naïve" and "Naive" stay distinct) **[AI choice]**. Stored titles are never rewritten.

## Public API

- **`sources` stays in the normalized JSON but is not in the API response. [requested]** It records which
  export each song came from, useful when auditing the data, but it is internal bookkeeping with no value for
  a frontend. The response model simply does not declare it.
- **Pagination. [requested defaults]** `page` defaults to 1, `size` to 10. `size` is capped at 100 **[AI
  choice]**. Invalid values return 422. A page past the end is an empty 200 with the real `total` and
  `total_pages`, not a 404 **[AI choice]**. An empty result has `total_pages` 0.
- **Global sorting. [requested]** The whole (filtered) result is sorted before the page is cut.
  `sort_by` accepts every field the API exposes, `rating` included, because the allowed values are derived
  from the response model **[AI choice]**. Direction is `asc` (default) or `desc`; values are case-sensitive.
  `order` without `sort_by` is ignored **[AI choice]**.
- **Nulls last in both directions. [AI choice]** Descending order does not put missing data on top.
- **Deterministic ties: by `id` ascending, in both directions. [requested: deterministic]** Results do not
  depend on the order of the data file. Titles sort case-insensitively **[AI choice]**; ids sort case-sensitively.
  No locale-aware collation, so accented letters sort after `z`.
- **Title search is a substring match. [changed from exact match after a bug report]** Typing part of a title
  (e.g. "Perf") must find the song on any page, so a search matches when the normalized title contains the
  normalized query. `title=perfect` returns both "Perfect" songs (and e.g. "Perfect Day"); `title=21` also
  returns "21 Guns". The comparison reuses the normalizer's title key (Unicode NFKC, case-folded,
  whitespace collapsed).
- **Blank `title` means no filter. [AI choice, needs approval]** `title=` and `title=%20` behave as if the
  parameter was omitted, which suits a cleared search box. Songs with a null title never match a real search.
- **Operation order: filter, sort, paginate. [requested]** `total` and `total_pages` describe the filtered set.
- **`rating` is part of the song response. [AI choice]** `null` until rated, so the frontend gets everything
  in one call. It is merged in per request; the stored dataset is never changed.
- **Startup validation. [requested: fail clearly]** The data file must be a JSON array of valid songs with
  unique ids; otherwise startup fails with the path and the offending item. Nothing in the app writes to the
  data files.
- **CORS is limited to `http://localhost:5173` and `http://127.0.0.1:5173`. [AI choice, needs approval]**
  Those are the Vite dev server origins, assumed for the planned React frontend (the `.gitignore` mentions
  `.vite/`). Only `GET`, `PUT` and the `Content-Type` header are allowed. No wildcard.

## Ratings

- **Storage: a SQLite file (`backend/data/ratings.db`) through Python's built-in `sqlite3`. [AI choice]** It
  needs no new dependency or server. Each rating is a single atomic upsert on one row, so rating one song cannot
  drop another's rating, and concurrent threads or processes are safe (SQLite serializes the writes). A JSON file
  would have needed hand-written locking and atomic-rename logic to get the same guarantees.
- **Kept separate from the song data. [requested]** `songs_normalized.json` is never written; ratings are
  merged into responses at request time. The file is gitignored (`*.db`), since it is runtime state.
- **Endpoints: `PUT /songs/{id}/rating` (create or replace, 200) and `GET /songs/{id}/rating`.** Ratings are
  also in `GET /songs`. Keyed by song `id`, never title, so duplicate titles do not collide.
- **Validation. [requested: sensible behaviour]** Only a JSON integer 1-5 is accepted (strings, floats,
  booleans, null, extra keys are 422); the table also has a `CHECK` constraint. An unknown id is 404, and is
  checked before the body, so a wrong id is always reported as such.
- **Limitations.** Single-machine, file-based storage with no per-user ratings (one rating per song, last
  write wins) and no way to remove a rating. Ratings for ids no longer in the dataset stay in the file and are
  ignored. Every `/songs` request reads all ratings, which is fine at this size. Anything beyond one host would
  need a real database.

## AI-assisted review and changes (only what happened in the sessions)

- **Environment.** The AI diagnosed a broken Homebrew `pyexpat` and proposed fixes. The first two (update
  Homebrew and Python, rebuild the venv) did not help. The `DYLD_LIBRARY_PATH` workaround worked in a test but
  was not adopted (later instructions ruled it out); a `uv`-managed Python was used instead. Recreating `backend/.venv` went against the instruction not to recreate it, so the AI asked
  first and recreated it only after approval.
- **Normalizer review.** The AI reviewed its own normalizer on request. It found minor bugs and gaps: a
  within-file duplicate id was counted as appearing in multiple sources, `"1_0"` was accepted as a number, the
  `valence` fill reason was misleading, a fill dropped the invalid original value, and duplicate-title detection
  was case-sensitive. These were fixed in a follow-up prompt, with regression tests; the normalized data did not change.
- **Tests were checked for usefulness.** The AI injected bugs into scratch copies of the code (page-only
  sorting, a lossy ratings write, wrong filter order, wildcard CORS and others) and confirmed the suite fails each
  time. One of its own tests rested on a wrong assumption about the test data and was rewritten, and a test that
  would have failed for anyone who had run the app was replaced by a session-level check.
- **`sources` removed from the response** at the user's request after the first API version exposed it.
