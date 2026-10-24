# Prompts

An honest record of the AI-assisted work in one Claude Code conversation, written by the AI at the user's
request from that conversation's history.

- **Verbatim** entries are exact quotes. **Paraphrase** entries summarise a longer prompt; they are not the
  original wording, which in these cases is much longer than shown.
- Work before this conversation (the project scaffold, `.gitignore`, and the commit adding `requirements.txt`) is
  not covered, because those prompts are not available here.
- "Outcome" says what was accepted or changed. Anything the AI proposed that was not acted on is not described as done.

## 1. Python environment

The conversation began with the user pasting a `pyexpat` `ImportError` traceback from the project's venv, with no
instruction.

| Prompt | Purpose | Outcome |
|---|---|---|
| *(pasted traceback)* | Diagnose the import failure | AI explained that Homebrew's `pyexpat` did not match macOS's system `libexpat` and offered four options. Nothing was run. |
| "run steps 1-2 for me" (verbatim) | Run the Homebrew upgrade and venv rebuild | Neither fixed it (`expat` is keg-only; `ensurepip` still failed). A `DYLD_LIBRARY_PATH` test worked, and the AI recommended `uv` instead. |
| "yes, set up the uv venv" (verbatim) | Avoid the library-path workaround | `uv` installed with Homebrew; venv created with uv's managed Python 3.13.17; `pyexpat` imports. |
| "is the venv setup?" (verbatim) | Check the state | AI answered that the venv worked but was empty (no packages, no `pip`). |

## 2. Backend dependencies

- **Paraphrase:** inspect `backend/`, create `requirements.txt` (FastAPI, Uvicorn, pytest, HTTPX if needed),
  use the existing `backend/.venv`, do not recreate it, install with `uv pip`, run any tests, no `DYLD_LIBRARY_PATH`,
  report files and commands.
- **Purpose:** reproducible install.
- **Outcome:** `app/` and `tests/` were empty, so only dependencies were set up. The existing `backend/.venv` turned
  out to use the broken Homebrew Python, so `uv pip` refused it. The AI asked rather than deleting it; the user chose
  recreation with uv. 22 packages installed.

## 3. Normalization

1. **Data audit** (paraphrase). Look through the two JSON files and report inconsistencies (duplicates that
   disagree, missing or invalid values, attribute differences, suspicious numbers, especially `duration_ms` units,
   title formatting, structure). Investigate only; change nothing. *Outcome:* a report with examples and a
   "definite problem vs needs investigation" label for each issue, and a list of decisions for the user. Findings
   included three `duration_ms` values in seconds, an invalid `danceability` 1.42, `acousticness` -0.05, `tempo` 0, and
   two distinct "Perfect" songs.
2. **Implement the normalizer** (paraphrase). Dedupe on `id`; part 1 wins conflicts but disagreements go to a
   separate quality report; nulls for missing and invalid values with reasons, no clamping; a conservative rule for
   seconds-vs-milliseconds with every correction recorded; keep `valence`; trim titles without guessing; tests for
   duplicates, conflicts, missing fields, invalid numbers, duration and the two "Perfect" songs. *Outcome:*
   `normalizer.py`, the two output files and 36 tests. The AI added choices the prompt did not specify (fill from
   the other file when the winning value is unusable; a segment-count cross-check for the duration rule) and
   listed them as assumptions to review.
3. **Review the implementation** (paraphrase). Check it follows the agreed rules; look at fallback behaviour,
   whether duration correction can change a legitimate value, whether the report covers every transformation, and
   test coverage; don't change code. *Outcome:* the AI confirmed all 25 ids and unchanged sources, found no bug
   affecting the data, but reported minor bugs and test gaps (see DECISIONS.md).
4. **Fixes and test improvements** (paraphrase). Fix within-file duplicate accounting, reject strings like `"1_0"`,
   correct the `valence` fill reason, keep the invalid original in fill records, add boundary tests, strengthen the
   weak assertions and the determinism test, document the fill and null rules, make duplicate-title detection
   consistent. *Outcome:* all done; the normalized dataset did not change. The AI also checked the new tests by
   injecting bugs into scratch copies.
5. **Branch and commit** (paraphrase of a short prompt: create `feature/data-normalization` if on `main`, commit
   only the normalization files, message "Implement song data normalization"), then **"push the branch"**
   (verbatim). *Outcome:* committed and pushed; `requirements.txt` was already on `main`, so it was not part of the commit.

## 4. API

1. **Foundation and pagination** (paraphrase). FastAPI app with a clear entry point; load the normalized file
   independent of the working directory; keep loading separate from routes; `GET /songs` with `page` and `size`
   (defaults 1 and 10), clear response structure, validation, tests for default, custom, first and last pages, empty
   page, invalid values and metadata. *Outcome:* implemented. Choices the prompt left open and the AI made:
   `size` capped at 100, an out-of-range page returns an empty 200.
2. **Hide `sources`** (paraphrase). Keep `sources` in the normalized JSON, omit it from the public response unless
   something needs it; check tests; create `feature/songs-api` from the current branch; don't commit or push.
   *Outcome:* nothing used it, so it was dropped from the response model and tests were updated.
3. **Global sorting** (paraphrase). Optional `sort_by` and `order`; validate with 422; sort the whole dataset before
   paginating; consistent nulls; deterministic ties; tests including one that fails if sorting only happened within
   a page. *Outcome:* implemented with nulls last in both directions and id tie-breaks. The AI confirmed the
   "page-only sort" test fails when that bug is injected. One of its own test assumptions was wrong and was corrected.

## 5. Remaining backend work

- **Paraphrase:** inspect the code and assignment, then in one pass add title search (case, whitespace, empty
  search, order filter then sort then paginate), persistent ratings by song id (simplest storage, validation,
  concurrency, tests, kept apart from song data), robustness review (validation, startup failures, CORS limited to
  the dev origin, `sources` still hidden), comprehensive tests, a live run, and README and `DECISIONS.md`; leave
  `PROMPTS.md`/`REFLECTION.md` alone; stay on `feature/songs-api`, no commit or push.
- **Interruption and clarification:** the first attempt was interrupted by the user and the prompt re-sent with an
  added clarification (paraphrase): `DECISIONS.md` and `PROMPTS.md` do not exist, so create both, record only real
  decisions and history, label paraphrases, and do not invent or misattribute.
- **Outcome:** title search, SQLite ratings and CORS were implemented, with new tests (search, ratings,
  robustness) and updated docs. Where the prompt was silent the AI chose and recorded it in DECISIONS.md. Three of
  those choices are marked there as needing the user's approval.
- **Not done:** no assignment brief or `REVIEW.md` was found in the repo (only `review/buggy_api.py`, an unrelated
  review exercise), so "assignment requirements" were taken from the prompts alone. `REFLECTION.md` was not created.
