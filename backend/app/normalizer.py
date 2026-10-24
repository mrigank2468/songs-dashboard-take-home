"""Normalize the two song-catalog exports into one canonical dataset.

The inputs are column-oriented JSON (``{column: {row_index: value}}``).  The
output is a deduplicated list of records plus a data-quality report that
records every change, fill and disagreement.  Original files are never
modified, and nothing is clamped or invented: invalid values become ``None``
with a recorded reason.

Everything here is a pure function of its inputs except ``run``, which does
the file I/O.
"""

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Source files in precedence order: earlier sources win on conflicts.
SOURCES = (
    ("part1", "songs_part1.json"),
    ("part2", "songs_part2.json"),
)
DATASET_FILE = "songs_normalized.json"
REPORT_FILE = "data_quality_report.json"

FIELDS = (
    "id",
    "title",
    "danceability",
    "energy",
    "mood",
    "acousticness",
    "tempo",
    "duration_ms",
    "num_sections",
    "num_segments",
    "valence",
)
UNIT_INTERVAL_FIELDS = ("danceability", "energy", "acousticness", "valence")
POSITIVE_INT_FIELDS = ("num_sections", "num_segments")

# Strings (case-insensitive, after stripping) that mean "no value".
NULL_STRINGS = frozenset({"", "n/a", "na", "null", "none", "nan"})

# The only numeric-string format accepted: optional sign, ASCII digits and an
# optional decimal point.  No underscores, exponents, inf/nan or other digits.
NUMERIC_STRING = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)")

# Tempo is in BPM.  0 is a placeholder, not a tempo; the upper bound is a
# generous sanity limit (no real song is near it).
TEMPO_MAX_BPM = 400.0

# --- duration_ms seconds-vs-milliseconds rule --------------------------------
# A value is only treated as seconds when ALL of the following hold:
#   1. it is below SECONDS_SUSPECT_BELOW_MS (no real song lasts under 1 s);
#   2. the corrected value (x1000) is a plausible song length; and
#   3. the corrected value agrees with num_segments: the implied milliseconds
#      per segment falls in a range that the well-formed rows sit inside
#      (observed ~207-342 ms/segment; a x1000 error shows up as ~0.2-0.3).
# If (1) holds but (2) or (3) cannot be confirmed, the value is nulled and
# reported rather than guessed at.
SECONDS_SUSPECT_BELOW_MS = 1000
PLAUSIBLE_SONG_MS = (30_000, 30 * 60_000)
PLAUSIBLE_MS_PER_SEGMENT = (100.0, 600.0)
SECONDS_TO_MS = 1000


class _Missing:
    """Sentinel for a key that is absent from a source row."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


# --- loading ----------------------------------------------------------------


def rows_from_columns(columns: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Rebuild ``(row_index, row)`` pairs from a column-oriented mapping.

    Rows are ordered by numeric index.  A column with no entry for a row index
    leaves that key out of the row, so absence stays distinguishable from null.
    """
    indexes: set[str] = set()
    for column in columns.values():
        indexes.update(column)

    def sort_key(index: str) -> tuple[int, int, str]:
        return (0, int(index), index) if index.isdigit() else (1, 0, index)

    rows = []
    for index in sorted(indexes, key=sort_key):
        rows.append((index, {name: col[index] for name, col in columns.items() if index in col}))
    return rows


def load_columns(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# --- value cleaning ---------------------------------------------------------


def _is_null_like(value: Any) -> str | None:
    """Return how the value is missing ('missing_key', 'null', 'empty_string',
    'placeholder_string'), or None if it carries a value."""
    if value is MISSING:
        return "missing_key"
    if value is None:
        return "null"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return "empty_string"
        if stripped.lower() in NULL_STRINGS:
            return "placeholder_string"
    return None


def _to_number(value: Any) -> tuple[float | None, bool]:
    """Parse a number.  Returns ``(number, was_string)``; number is None when
    the value is not a finite number.  Booleans are rejected."""
    if isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        number = float(value)
        return (number if math.isfinite(number) else None), False
    if isinstance(value, str):
        text = value.strip()
        # float() alone also accepts "1_0", "1e5", "inf" and non-ASCII digits.
        if not NUMERIC_STRING.fullmatch(text):
            return None, True
        number = float(text)
        return (number if math.isfinite(number) else None), True
    return None, False


def _to_int(value: Any) -> tuple[int | None, bool]:
    """Like ``_to_number`` but only accepts whole numbers."""
    number, was_string = _to_number(value)
    if number is None or not number.is_integer():
        return None, was_string
    return int(number), was_string


def _clean_field(field: str, raw: Any) -> tuple[Any, str | None, str | None]:
    """Clean one non-duration, non-id field.

    Returns ``(value, issue, reason)``.  ``issue`` is None when the value was
    used as given, ``'type_coercion'`` when a numeric string was converted,
    ``'missing_value'`` when it normalized to null because nothing was there,
    and ``'invalid_value'`` when a present value was rejected.
    """
    missing_how = _is_null_like(raw)
    if missing_how is not None:
        return None, "missing_value", missing_how

    if field == "title":
        if not isinstance(raw, str):
            return None, "invalid_value", "title_not_a_string"
        trimmed = raw.strip()
        if trimmed != raw:
            return trimmed, "title_trimmed", "surrounding_whitespace_removed"
        return trimmed, None, None

    if field == "mood":
        value, was_string = _to_int(raw)
        if value is None:
            return None, "invalid_value", "not_an_integer"
        if value not in (0, 1):
            return None, "invalid_value", "mood_not_0_or_1"
        return value, ("type_coercion" if was_string else None), ("numeric_string_converted" if was_string else None)

    if field in POSITIVE_INT_FIELDS:
        value, was_string = _to_int(raw)
        if value is None:
            return None, "invalid_value", "not_an_integer"
        if value < 1:
            return None, "invalid_value", "not_positive"
        return value, ("type_coercion" if was_string else None), ("numeric_string_converted" if was_string else None)

    number, was_string = _to_number(raw)
    if number is None:
        return None, "invalid_value", "not_a_number"
    if field in UNIT_INTERVAL_FIELDS and not 0.0 <= number <= 1.0:
        return None, "invalid_value", "out_of_range_0_to_1"
    if field == "tempo":
        if number <= 0:
            return None, "invalid_value", "tempo_not_positive"
        if number > TEMPO_MAX_BPM:
            return None, "invalid_value", f"tempo_above_{TEMPO_MAX_BPM:g}_bpm"
    return number, ("type_coercion" if was_string else None), ("numeric_string_converted" if was_string else None)


def clean_duration(raw: Any, num_segments: int | None) -> tuple[int | None, str | None, str | None]:
    """Clean ``duration_ms``, applying the conservative seconds rule.

    ``num_segments`` must already be cleaned (None if unusable).  Returns
    ``(value, issue, reason)`` with issue in {None, 'type_coercion',
    'missing_value', 'invalid_value', 'duration_correction'}.
    """
    missing_how = _is_null_like(raw)
    if missing_how is not None:
        return None, "missing_value", missing_how

    number, was_string = _to_number(raw)
    if number is None:
        return None, "invalid_value", "not_a_number"
    if number <= 0:
        return None, "invalid_value", "not_positive"
    if not number.is_integer():
        return None, "invalid_value", "not_an_integer"
    value = int(number)

    if value >= SECONDS_SUSPECT_BELOW_MS:
        return value, ("type_coercion" if was_string else None), ("numeric_string_converted" if was_string else None)

    corrected = value * SECONDS_TO_MS
    low, high = PLAUSIBLE_SONG_MS
    if not low <= corrected <= high:
        return None, "invalid_value", "below_1s_and_corrected_value_not_a_plausible_song_length"
    if num_segments is None:
        return None, "invalid_value", "below_1s_and_unverifiable_without_num_segments"
    ms_per_segment = corrected / num_segments
    seg_low, seg_high = PLAUSIBLE_MS_PER_SEGMENT
    if not seg_low <= ms_per_segment <= seg_high:
        return None, "invalid_value", "below_1s_and_corrected_value_disagrees_with_num_segments"
    return corrected, "duration_correction", (
        f"treated_as_seconds: value<{SECONDS_SUSPECT_BELOW_MS}, x{SECONDS_TO_MS} gives a plausible "
        f"song length and {ms_per_segment:.0f} ms/segment (accepted {seg_low:g}-{seg_high:g})"
    )


# --- record normalization ---------------------------------------------------


def _jsonable(value: Any) -> Any:
    return None if value is MISSING else value


def clean_record(
    source: str, row_index: str, row: dict[str, Any], unprovided: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Clean one source row.

    ``unprovided`` names columns the source does not have at all; they clean
    to None without a per-row issue (the report lists them once, per source,
    under ``schema``).

    Returns ``{"id", "source", "row", "values", "raw", "status", "unprovided",
    "issues"}``.  ``values`` maps each field to its cleaned value (None if
    unavailable), ``raw`` to the original value (MISSING if absent), ``status``
    to ``(issue, reason)`` from cleaning (including for unprovided columns,
    which ``issues`` leaves out) and ``issues`` lists the per-field changes.
    ``id`` is None when the row has no usable id.
    """
    raw_id = row.get("id", MISSING)
    record_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None

    values: dict[str, Any] = {"id": record_id}
    raws: dict[str, Any] = {name: row.get(name, MISSING) for name in FIELDS}
    status: dict[str, tuple[str | None, str | None]] = {}
    issues: list[dict[str, Any]] = []

    def note(field: str, issue: str, reason: str, value: Any) -> None:
        issues.append(
            {
                "id": record_id,
                "source": source,
                "row": row_index,
                "field": field,
                "issue": issue,
                "original": _jsonable(raws[field]),
                "value": value,
                "reason": reason,
            }
        )

    if record_id is not None and record_id != raw_id:
        note("id", "id_trimmed", "surrounding_whitespace_removed", record_id)

    for field in FIELDS:
        if field in ("id", "duration_ms"):
            continue
        value, issue, reason = _clean_field(field, raws[field])
        values[field] = value
        status[field] = (issue, reason)
        if issue and field not in unprovided:
            note(field, issue, reason, value)

    value, issue, reason = clean_duration(raws["duration_ms"], values["num_segments"])
    values["duration_ms"] = value
    status["duration_ms"] = (issue, reason)
    if issue and "duration_ms" not in unprovided:
        note("duration_ms", issue, reason, value)

    return {
        "id": record_id,
        "source": source,
        "row": row_index,
        "values": values,
        "raw": raws,
        "status": status,
        "unprovided": unprovided,
        "issues": issues,
    }


def _primary_status(base: dict[str, Any], field: str) -> tuple[str, str | None]:
    """Why the primary record has no value for ``field``: the column does not
    exist in its source, the value was missing, or it was present but invalid."""
    if field in base["unprovided"]:
        return "column_not_provided", None
    issue, reason = base["status"][field]
    return issue or "missing_value", reason


def _merge(
    base: dict[str, Any],
    other: dict[str, Any],
    conflicts: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> None:
    """Fold ``other`` into ``base`` in place.  ``base`` wins on conflicts."""
    for field in FIELDS:
        if field == "id":
            continue
        kept, incoming = base["values"][field], other["values"][field]
        if incoming is None:
            continue
        if kept is None:
            base["values"][field] = incoming
            why, detail = _primary_status(base, field)
            explanation = {
                "column_not_provided": f"{base['source']} does not provide this column",
                "missing_value": f"{base['source']} value was missing ({detail})",
                "invalid_value": f"{base['source']} value was invalid ({detail}) and was nulled",
            }[why]
            fills.append(
                {
                    "id": base["id"],
                    "field": field,
                    "primary_source": base["source"],
                    "primary_row": base["row"],
                    "primary_status": why,
                    "primary_original": _jsonable(base["raw"][field]),
                    "primary_reason": detail,
                    "filled_from": other["source"],
                    "filled_from_row": other["row"],
                    "value": incoming,
                    "original": _jsonable(other["raw"][field]),
                    "reason": f"{explanation}; used {other['source']} value",
                }
            )
        elif kept != incoming:
            conflicts.append(
                {
                    "id": base["id"],
                    "title": base["values"]["title"],
                    "field": field,
                    "chosen_source": base["source"],
                    "chosen_row": base["row"],
                    "chosen_value": kept,
                    "chosen_original": _jsonable(base["raw"][field]),
                    "other_source": other["source"],
                    "other_row": other["row"],
                    "other_value": incoming,
                    "other_original": _jsonable(other["raw"][field]),
                    "reason": f"sources disagree; {base['source']} takes precedence",
                }
            )


def normalize(sources: list[tuple[str, dict[str, dict[str, Any]]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize ``[(source_name, columns), ...]`` (highest precedence first).

    Returns ``(dataset, report)``.  Dataset order is first appearance by
    source order then row index, so output is deterministic.
    """
    merged: dict[str, dict[str, Any]] = {}
    origins: dict[str, list[str]] = {}
    cleaning_issues: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    within_source_duplicates = 0
    schema: dict[str, Any] = {}
    row_counts: dict[str, int] = {}

    for source, columns in sources:
        rows = rows_from_columns(columns)
        row_counts[source] = len(rows)
        not_provided = [f for f in FIELDS if f not in columns]
        schema[source] = {"columns": sorted(columns), "fields_not_provided": not_provided}
        for row_index, row in rows:
            record = clean_record(source, row_index, row, frozenset(not_provided))
            cleaning_issues.extend(record["issues"])
            record_id = record["id"]
            if record_id is None:
                dropped.append(
                    {
                        "source": source,
                        "row": row_index,
                        "reason": "missing_or_empty_id",
                        "original_row": {k: _jsonable(v) for k, v in record["raw"].items()},
                    }
                )
                continue
            if record_id not in merged:
                merged[record_id] = record
                origins[record_id] = [source]
                continue
            _merge(merged[record_id], record, conflicts, fills)
            if source in origins[record_id]:
                within_source_duplicates += 1
            else:
                origins[record_id].append(source)

    dataset = []
    for record_id, record in merged.items():
        dataset.append({**{f: record["values"][f] for f in FIELDS}, "sources": origins[record_id]})

    title_groups: dict[str, list[dict[str, Any]]] = {}
    for record in dataset:
        if record["title"] is not None:
            title_groups.setdefault(title_key(record["title"]), []).append(record)
    duplicate_titles = [
        {
            "title": group[0]["title"],
            "titles": list(dict.fromkeys(r["title"] for r in group)),
            "ids": [r["id"] for r in group],
            "action": "kept_all_records: ids differ, so they are treated as distinct songs",
        }
        for group in title_groups.values()
        if len(group) > 1
    ]

    report = {
        "summary": {
            "input_rows": row_counts,
            "unique_ids": len(dataset),
            "ids_in_multiple_sources": sum(1 for s in origins.values() if len(s) > 1),
            "duplicate_rows_within_a_source": within_source_duplicates,
            "dropped_records": len(dropped),
            "conflicts": len(conflicts),
            "filled_from_other_source": len(fills),
            "duration_corrections": sum(1 for i in cleaning_issues if i["issue"] == "duration_correction"),
            "cleaning_issues_by_type": _count_by(cleaning_issues, "issue"),
        },
        "schema": schema,
        "conflicts": conflicts,
        "filled_from_other_source": fills,
        "duration_corrections": [i for i in cleaning_issues if i["issue"] == "duration_correction"],
        "cleaning_issues": [i for i in cleaning_issues if i["issue"] != "duration_correction"],
        "duplicate_titles": duplicate_titles,
        "dropped_records": dropped,
        "rules": {
            "dedupe_key": "id (surrounding whitespace trimmed)",
            "precedence": [name for name, _ in sources],
            "conflict_rule": (
                "both sources have a valid value and they differ: the earlier source in "
                "'precedence' is kept and the disagreement is listed under 'conflicts'"
            ),
            "fill_rule": (
                "the kept source has no value for a field (column_not_provided, missing_value or "
                "invalid_value) and a later source has a valid one: the later source's value is "
                "used and listed under 'filled_from_other_source' with the kept source's original "
                "value and reason. A later source never overrides a valid earlier value."
            ),
            "null_like_values": {
                "forms": ["missing_key", "null", "empty_string", "placeholder_string"],
                "placeholder_strings": sorted(s for s in NULL_STRINGS if s),
                "note": "matched case-insensitively after trimming; an empty or whitespace-only string is empty_string",
            },
            "numeric_string_format": NUMERIC_STRING.pattern,
            "duplicate_title_key": "NFKC-normalized, casefolded, whitespace-collapsed; diacritics are not folded",
            "unit_interval_fields": list(UNIT_INTERVAL_FIELDS),
            "tempo_valid_range_bpm": f"(0, {TEMPO_MAX_BPM:g}]",
            "duration_seconds_rule": {
                "suspect_below_ms": SECONDS_SUSPECT_BELOW_MS,
                "plausible_song_ms": list(PLAUSIBLE_SONG_MS),
                "plausible_ms_per_segment": list(PLAUSIBLE_MS_PER_SEGMENT),
            },
        },
    }
    return dataset, report


def title_key(title: str) -> str:
    """Key for spotting duplicate titles only; stored titles are never changed.

    NFKC unifies equivalent Unicode forms (e.g. "e" + combining accent vs a
    precomposed "é"), casefold ignores case, and whitespace runs collapse.
    Diacritics are NOT folded: "Naïve" and "Naive" stay different.
    """
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item[key]] = counts.get(item[key], 0) + 1
    return dict(sorted(counts.items()))


# --- entry point ------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(data_dir: Path = DATA_DIR) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the source exports from ``data_dir`` and write the normalized
    dataset and data-quality report next to them."""
    sources = [(name, load_columns(data_dir / filename)) for name, filename in SOURCES]
    dataset, report = normalize(sources)
    _write_json(data_dir / DATASET_FILE, dataset)
    _write_json(data_dir / REPORT_FILE, report)
    return dataset, report


if __name__ == "__main__":
    ds, rep = run()
    print(f"wrote {len(ds)} records; summary: {json.dumps(rep['summary'])}")
