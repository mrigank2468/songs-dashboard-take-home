# Prompts

An honest record of the AI-assisted work in one Claude Code conversation, written by the AI at the user's
request from that conversation's history.

- **Verbatim** entries are exact quotes. **Paraphrase** entries summarise a longer prompt; they are not the
  original wording, which in these cases is much longer than shown.
- Work before this conversation (the project scaffold, `.gitignore`, and the commit adding `requirements.txt`) is
  not covered, because those prompts are not available here.
- "Outcome" says what was accepted or changed. Anything the AI proposed that was not acted on is not described as done.
- Sections 5 to 7, the notes and the index were added later, after the conversation record was checked. The session
  log is described next.

## Session log

- **Where it is:** the conversation export is `claude_log.txt` at the root of this repository (about 151 KB). It
  has not been audited for sensitive content. There is no shareable link to the session.
- **What the line numbers mean:** the "Log line" numbers below refer to the original machine-readable Claude Code
  transcript (one JSON object per line), which is kept locally and is not part of the repository, so they do not
  correspond to lines of `claude_log.txt`. They are there so each entry can be checked against that original.
- **Span:** first message 2026-10-24 05:56 UTC. The index below runs to log line 1411 (2026-10-25 06:01 UTC); later
  messages are not listed. Commit timestamps in this repository show a UTC+05:30 offset, so local time is 5 h 30 min later.
- **Contents up to that point:** 30 user-role entries. Five are not prompts (the `/model` command and its output, a
  `[Request interrupted by user]` marker, and the `/export` command and its output), leaving 25 real messages, 15 of
  them pasted blocks and 10 typed directly.
- **Verbatim quotes** were copied from the original conversation record. **Paraphrases** are labelled.
- **A second, earlier log** (also local and not included) exists from a session started 2026-10-24 05:26 UTC in
  the home directory, not this project. Its only user entries are `hi`, `/plan` and `/model`. Neither log contains the prompts behind the project scaffold, `.gitignore` or the first
  `requirements.txt` commit, so those remain undocumented.

## 1. Backend dependencies

- **Paraphrase:** inspect `backend/`, create `requirements.txt` (FastAPI, Uvicorn, pytest, HTTPX if needed),
  use the existing `backend/.venv`, do not recreate it, install with `uv pip`, run any tests,
  report files and commands.
- **Purpose:** reproducible install.
- **Outcome:** `app/` and `tests/` were empty, so only dependencies were set up. The existing `backend/.venv` could not
  be used by `uv pip`. The AI asked rather than deleting it; the user chose recreation with uv. 22 packages installed.

## 2. Normalization

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

## 3. API

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

## 4. Remaining backend work

- **Paraphrase:** inspect the code and assignment, then in one pass add title search (case, whitespace, empty
  search, order filter then sort then paginate), persistent ratings by song id (simplest storage, validation,
  concurrency, tests, kept apart from song data), robustness review (validation, startup failures, CORS limited to
  the dev origin, `sources` still hidden), comprehensive tests, a live run, and README and `DECISIONS.md`; leave
  `PROMPTS.md`/`REFLECTION.md` alone; stay on `feature/songs-api`, no commit or push.
- **Interruption and clarification:** the first attempt was interrupted by the user and the prompt re-sent with an
  added clarification (paraphrase): `DECISIONS.md` and `PROMPTS.md` do not exist, so create both, record only real
  decisions and history, label paraphrases, and do not invent or misattribute. The exact sequence is in the notes below.
- **Outcome:** title search, SQLite ratings and CORS were implemented, with new tests (search, ratings,
  robustness) and updated docs. Where the prompt was silent the AI chose and recorded it in DECISIONS.md. Three of
  those choices are marked there as needing the user's approval.
- **Not done:** no assignment brief or `REVIEW.md` was found in the repo (only `review/buggy_api.py`, an unrelated
  review exercise), so "assignment requirements" were taken from the prompts alone. `REFLECTION.md` was not created.

## 5. Frontend

### Prompt 5.1: build the dashboard (log line 929)

- **Verbatim opening:** "We have completed the backend for a full-stack song dashboard take-home assignment. Now implement the frontend using the existing backend and its actual API contracts."
- **Paraphrase of the rest** (the original is about 4,500 characters):
  - Inspect the repo, README and backend first, without rewriting backend code.
  - Use React, TypeScript, Vite and Material UI with plain CSS (no Tailwind, no MUI Data Grid, no state library).
  - Table with title, tempo, danceability, energy, mood, duration, valence and rating, 10 per page, with loading, error and empty states.
  - Server-side sorting through `TableSortLabel` that resets to page 1.
  - Debounced (about 300 ms) title search that resets to page 1 and ignores stale requests.
  - A 1 to 5 rating dropdown that does not show a failed save as successful.
  - CSV export of the displayed page with correct escaping.
  - An API base URL taken from an environment variable and kept compatible with the backend's CORS origins.
  - Tests for parameters, paging, sorting, search, CSV and ratings; build and test runs; the full backend suite; a local run of both
    apps together; confirmation that the data files are unchanged; a README update.
  - No `REVIEW.md` or `REFLECTION.md` yet, no commits, and no unrelated backend changes.
- **Purpose:** the user-facing half of the assignment, built on the actual API.
- **Outcome:**
  - **Build:** `frontend/` was scaffolded with the Vite React-TypeScript template, plus MUI, Vitest and Testing Library. The app code is in `frontend/src/`: `api.ts`, `App.tsx`, `SongTable.tsx`, `RatingSelect.tsx`, `csv.ts`, `format.ts`, `columns.ts`.
  - **Checks run:** 81 frontend tests passed in 4 files; the build and lint passed; 396 backend tests passed; the four data files matched the checksums recorded before the work.
  - **Mutation check:** the AI injected 18 bugs into scratch copies of the frontend (stale responses, missing page resets, missing trim, broken CSV quoting, a failed rating shown as saved, and others) and the tests caught all 18.
  - **Integration check:**
    - The real `<App/>` ran against the real backend (on a throwaway ratings database) in a temporary jsdom test that was then deleted. It covered paging, global sorting, nulls last, search, rating and the CSV row.
    - A rating survived a backend restart.
    - CORS was verified with `curl` from both allowed origins.
    - The Vite dev server refused to start on another port.
  - **Not done:** no real browser was used, so layout and responsiveness were not checked.
  - **Flagged for the user's decision:**
    - "Unrated" is disabled once a song is rated, because the backend has no delete endpoint.
    - The CSV uses raw API values and field names.
    - The CSV starts with a UTF-8 BOM.
  - **Documentation:** the README was updated with setup, environment, commands, features and limitations. Neither `DECISIONS.md` nor this file was updated for the frontend at that point.

### Prompt 5.2: resume (log line 1170)

- **Verbatim (typo included):** "continue thwe leftover task"
- **Purpose (inferred):** the previous turn had ended before the README update and the final verification, so the user asked for the rest.
- **Outcome:** the AI stopped the dev servers and removed its temporary files, updated the README, and ran the final
  verification (396 backend tests, 81 frontend tests, build, lint, and the data files identical to the recorded checksums).

### Prompt 5.3: how to run the backend (log line 1204)

- **Verbatim:** "what command to run backend"
- **Purpose:** a quick usage question.
- **Outcome:** the AI answered `cd backend`, `source .venv/bin/activate`, `uvicorn app.main:app --reload`, with the
  server on port 8000 and docs at `/docs`. No files changed.

## 6. Code review of the generated API

### Prompt 6.1: write `REVIEW.md` (log line 1217)

- **Verbatim opening:** "Read review/buggy_api.py carefully and create a root-level REVIEW.md."
- **Paraphrase of the rest:** a pull-request-style review of `review/buggy_api.py`. For each finding give a priority (P1 or P2), a short
  title, the specific problem, a one-line impact and a practical fix. It should cover pagination and sorting, query and rating validation,
  title lookup and duplicates, rating identity, persistence and mutation, data loading and caching, status codes and error handling, duration statistics, and the response contract. It
  should avoid duplicate or padded findings, and must not modify `review/buggy_api.py` or the backend.
- **Purpose:** the review part of the assignment.
- **Outcome:**
  - **Review:** `REVIEW.md` has 15 findings (9 P1, 6 P2) and a closing table of how the submitted backend avoids them.
  - **Verification:** before writing, the AI ran the unmodified buggy file against a copy of the normalized data in a scratch directory. It reproduced most findings, such as the off-by-one page, page-only sorting, the 500 on null sort values, duplicate-title rating collisions and unvalidated ratings. The review marks which findings it reproduced and which come from reading the code, such as the `/stats/duration` crash on empty or null data.
  - **Files:** `review/buggy_api.py` and `backend/` were unchanged.
  - **Note:** the review says the submitted backend has no `/stats/duration` endpoint.

## 7. Documentation of the process

### Prompt 7.1: update this file (log line 1271)

- **Verbatim:** "Update `PROMPTS.md` only. Preserve all existing content. Review the actual Claude Code session history for this assignment, add any missing important prompts (especially frontend, testing, and integration), and briefly document each prompt's purpose and outcome. Link the actual session log if accessible; never invent prompts, outcomes, or file paths. Label paraphrases clearly. Do not modify other files, commit, or push."
- **Purpose:** make this record complete and checkable against the real log.
- **Outcome:** the frontend, follow-up and review prompts, the session-log notes and an index of every message were added
  below the original content. No other file was changed.

### Prompt 7.2: remove the machine-specific log path (log line 1355)

- **Verbatim:** "Update PROMPTS.md only. Keep the existing history and addendum intact, but replace the machine-specific Claude session-log path with a clear note that the full log is available locally and is not included in the repository. Add a shareable session link only if a real, accessible URL exists. Do not copy the private transcript into the repo, invent a URL, or modify any other file."
- **Purpose:** keep the local username and directory layout out of the document and avoid implying a link that does not exist.
- **Outcome:** both local transcript paths were replaced by a plain note. The AI searched the logs for a shareable session URL
  and found none, so none was added. No other file was changed.

### Prompt 7.3: remove the environment troubleshooting and reorder (log line 1411)

- **Verbatim (typos included):** "remove that pyhton fixing error from prompt.md that and reorder it"
- **Follow-up after an interruption** (verbatim, typos included; not in the index below because it is after log line 1411):
  "no read to re-read the log just change in the session log point it to claude_log.txt". The AI had started to re-read the
  log to refresh the counts; the user interrupted and asked for the session-log note to point at `claude_log.txt` instead.
- **Purpose:** drop the Python environment troubleshooting from the record and make the document read in order.
- **Outcome:**
  - The Python environment troubleshooting section (four prompts) was removed. The index still
    lists those four messages, marked as omitted, so the index stays a complete list of messages.
  - One sentence in section 1 that referred to the environment problem was shortened to the fact that the existing
    `backend/.venv` could not be used, and a related clause was dropped from that section's paraphrase.
  - The sections were renumbered 1 to 7 in chronological order, the session-log note moved to the top, and the
    separate addendum was merged into the main structure.
  - The session-log note now points to `claude_log.txt`. The counts and the two newest prompts were taken from the
    earlier reading of the log, not re-read.
  - No other file was changed. `DECISIONS.md` and `README.md` still mention the environment issue; they were not
    edited because the request named this file only.

## Notes and corrections

- **Interruption in section 4.** The exact sequence in the log was: the "remaining backend" prompt (log line 633);
  an interruption (665); a separate clarification about `DECISIONS.md` and `PROMPTS.md` (667); the original prompt
  sent again, byte-identical to the first (672); and finally one combined message containing the original prompt
  followed by the clarification (683). The AI's work followed the combined message. Section 4's wording, "re-sent
  with an added clarification", is a fair summary of this.
- **Section 4, "Not done":** that note about `REVIEW.md` was accurate when written. `review/buggy_api.py` itself says
  `REVIEW.md` is part of the take-home, and it was created later (prompt 6.1).
- **Testing and integration prompts.** The log contains no separate testing or integration prompt. Those requirements
  were written into the feature prompts. Tests were requested in the normalizer, fixes, API pagination, sorting and
  remaining-backend prompts (sections 2 items 2 and 4, 3 items 1 and 3, and 4), and in the frontend prompt (5.1),
  whose "Verification and documentation" list asked for frontend tests, a build, the backend suite, a local run of
  both apps together, and a check that the data files were unchanged.

## Index of every user message in the session log

Runs to log line 1411. Times are UTC. "Log line" refers to the original local transcript (see the session-log note above).

| # | Log line | Time | Message | Documented in |
|---|---|---|---|---|
| 1 | 4-5 | 10-24 05:56 | `/model` command and its output (not a prompt) | n/a |
| 2 | 8 | 05:57 | pasted error traceback (environment troubleshooting) | omitted at the author's request |
| 3 | 49 | 05:58 | "run steps 1-2 for me" | omitted at the author's request |
| 4 | 83 | 05:58 | "yes, set up the uv venv" | omitted at the author's request |
| 5 | 96 | 05:59 | "is the venv setup?" | omitted at the author's request |
| 6 | 115 | 06:00 | backend dependency setup | section 1 |
| 7 | 172 | 06:06 | data audit | section 2, item 1 |
| 8 | 219 | 06:26 | implement the normalizer | section 2, item 2 |
| 9 | 294 | 06:36 | review the normalizer | section 2, item 3 |
| 10 | 318 | 06:43 | fixes and test improvements | section 2, item 4 |
| 11 | 418 | 06:52 | create branch and commit | section 2, item 5 |
| 12 | 454 | 06:53 | "push the branch" | section 2, item 5 |
| 13 | 473 | 07:14 | FastAPI foundation and pagination | section 3, item 1 |
| 14 | 537 | 07:20 | hide `sources`, new branch | section 3, item 2 |
| 15 | 580 | 07:22 | global sorting | section 3, item 3 |
| 16 | 633 | 07:29 | remaining backend work (first send) | section 4 |
| 17 | 665 | 07:30 | `[Request interrupted by user]` (not a prompt) | section 4, notes |
| 18 | 667 | 07:30 | clarification: create `DECISIONS.md` and `PROMPTS.md` | section 4, notes |
| 19 | 672 | 07:30 | the same prompt as 16, sent again | notes |
| 20 | 683 | 07:31 | combined prompt (16 plus 18) | section 4, notes |
| 21 | 929 | 08:02 | frontend dashboard | prompt 5.1 |
| 22 | 1170 | 08:14 | "continue thwe leftover task" | prompt 5.2 |
| 23 | 1204 | 08:19 | "what command to run backend" | prompt 5.3 |
| 24 | 1217 | 10-25 05:11 | write `REVIEW.md` | prompt 6.1 |
| 25 | 1271 | 05:33 | update `PROMPTS.md` (session log and index) | prompt 7.1 |
| 26 | 1355 | 05:37 | remove the machine-specific log path | prompt 7.2 |
| 27 | 1406-1407 | 05:42 | `/export` command and its output (not a prompt) | n/a |
| 28 | 1411 | 06:01 | remove the environment troubleshooting and reorder | prompt 7.3 |
