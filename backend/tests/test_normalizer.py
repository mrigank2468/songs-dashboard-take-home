import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import normalizer
from app.normalizer import normalize, rows_from_columns

REAL_DATA = Path(__file__).resolve().parent.parent / "data"


def song(id="a" * 22, **overrides):
    """A fully valid row; override or drop (value=...) fields per test."""
    row = {
        "id": id,
        "title": "Song",
        "danceability": 0.5,
        "energy": 0.6,
        "mood": 1,
        "acousticness": 0.1,
        "tempo": 120.0,
        "duration_ms": 200_000,
        "num_sections": 8,
        "num_segments": 800,
    }
    row.update(overrides)
    return row


def columns(*rows):
    """Build column-oriented input; a row value of ... omits that key."""
    cols: dict[str, dict[str, object]] = {}
    for i, row in enumerate(rows):
        for name, value in row.items():
            if value is ...:
                cols.setdefault(name, {})
                continue
            cols.setdefault(name, {})[str(i)] = value
    return cols


def run(part1_rows, part2_rows=()):
    sources = [("part1", columns(*part1_rows))]
    if part2_rows:
        sources.append(("part2", columns(*part2_rows)))
    return normalize(sources)


def by_id(dataset):
    return {r["id"]: r for r in dataset}


def issues_for(report, field, issue=None):
    return [
        i
        for i in report["cleaning_issues"] + report["duration_corrections"]
        if i["field"] == field and (issue is None or i["issue"] == issue)
    ]


def issues_for_all(report, issue):
    return [i for i in report["cleaning_issues"] + report["duration_corrections"] if i["issue"] == issue]


# --- structure ---------------------------------------------------------------


def test_rows_from_columns_keeps_missing_keys_absent_and_orders_numerically():
    rows = rows_from_columns({"a": {"10": 1, "2": 2}, "b": {"2": 3}})
    assert rows == [("2", {"a": 2, "b": 3}), ("10", {"a": 1})]


# --- duplicate reconciliation ------------------------------------------------


def test_same_id_across_sources_becomes_one_record_with_both_sources():
    dataset, report = run([song()], [song(valence=0.4)])
    assert len(dataset) == 1
    assert dataset[0]["sources"] == ["part1", "part2"]
    assert report["summary"]["ids_in_multiple_sources"] == 1
    assert report["conflicts"] == []


def test_valence_is_null_when_unavailable_and_filled_from_part2_when_present():
    dataset, report = run([song("a" * 22), song("b" * 22)], [song("b" * 22, valence=0.4)])
    records = by_id(dataset)
    assert records["a" * 22]["valence"] is None
    assert records["b" * 22]["valence"] == 0.4
    assert all("valence" in r for r in dataset)
    assert [f["field"] for f in report["filled_from_other_source"]] == ["valence"]
    assert report["conflicts"] == []
    assert report["schema"]["part1"]["fields_not_provided"] == ["valence"]


def test_first_occurrence_within_a_source_wins_and_conflict_is_recorded():
    part1 = columns(song(title="First"), song(title="Second"))
    dataset, report = normalize([("part1", part1)])
    assert [r["title"] for r in dataset] == ["First"]
    assert report["conflicts"][0]["other_value"] == "Second"


def test_row_without_id_is_reported_not_silently_dropped():
    dataset, report = run([song(id=None), song("b" * 22)])
    assert [r["id"] for r in dataset] == ["b" * 22]
    assert report["dropped_records"][0]["reason"] == "missing_or_empty_id"


# --- conflicting values -------------------------------------------------------


def test_conflict_uses_part1_and_records_both_original_values():
    dataset, report = run([song(danceability=0.727)], [song(danceability=0.74)])
    assert dataset[0]["danceability"] == 0.727
    (conflict,) = report["conflicts"]
    assert conflict["field"] == "danceability"
    assert conflict["chosen_source"] == "part1"
    assert (conflict["chosen_value"], conflict["other_value"]) == (0.727, 0.74)
    assert (conflict["chosen_original"], conflict["other_original"]) == (0.727, 0.74)


def test_conflict_compares_cleaned_values_so_string_and_number_do_not_conflict():
    _, report = run([song(danceability="0.5")], [song(danceability=0.5)])
    assert report["conflicts"] == []


def test_invalid_part1_value_is_filled_from_part2_and_reported():
    dataset, report = run([song(energy="N/A")], [song(energy=0.7)])
    assert dataset[0]["energy"] == 0.7
    (fill,) = report["filled_from_other_source"]
    assert (fill["field"], fill["filled_from"], fill["value"]) == ("energy", "part2", 0.7)
    assert report["conflicts"] == []


def test_part2_invalid_value_never_overrides_part1():
    dataset, report = run([song(energy=0.7)], [song(energy="N/A")])
    assert dataset[0]["energy"] == 0.7
    assert report["conflicts"] == [] and report["filled_from_other_source"] == []


# --- missing fields -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, how",
    [(..., "missing_key"), (None, "null"), ("", "empty_string"), ("  ", "empty_string"), ("N/A", "placeholder_string"), ("n/a", "placeholder_string")],
)
def test_missing_forms_all_normalize_to_null_with_recorded_form(raw, how):
    dataset, report = run([song(energy=raw)])
    assert dataset[0]["energy"] is None
    (issue,) = issues_for(report, "energy")
    assert (issue["issue"], issue["reason"], issue["value"]) == ("missing_value", how, None)


def test_missing_title_becomes_null():
    dataset, _ = run([song(title="  ")])
    assert dataset[0]["title"] is None


# --- invalid numeric values ---------------------------------------------------


def test_out_of_range_values_are_nulled_not_clamped():
    dataset, report = run(
        [song("a" * 22, danceability=1.42), song("b" * 22, acousticness=-0.05)]
    )
    records = by_id(dataset)
    assert records["a" * 22]["danceability"] is None
    assert records["b" * 22]["acousticness"] is None
    (issue,) = issues_for(report, "danceability")
    assert (issue["original"], issue["reason"]) == (1.42, "out_of_range_0_to_1")


def test_tempo_zero_is_invalid_and_recorded():
    dataset, report = run([song(tempo=0)])
    assert dataset[0]["tempo"] is None
    (issue,) = issues_for(report, "tempo")
    assert (issue["issue"], issue["original"], issue["reason"]) == ("invalid_value", 0, "tempo_not_positive")


def test_unparseable_and_non_finite_numbers_are_invalid():
    dataset, report = run([song("a" * 22, tempo="fast"), song("b" * 22, energy=float("inf"))])
    records = by_id(dataset)
    assert records["a" * 22]["tempo"] is None and records["b" * 22]["energy"] is None
    assert issues_for(report, "tempo")[0]["reason"] == "not_a_number"


def test_valid_numeric_strings_are_converted_and_recorded():
    dataset, report = run([song(danceability="0.521", tempo="108.73", mood="1")])
    assert dataset[0]["danceability"] == 0.521
    assert dataset[0]["tempo"] == 108.73
    assert dataset[0]["mood"] == 1
    coerced = {
        i["field"]: (i["original"], i["value"], i["reason"]) for i in issues_for_all(report, "type_coercion")
    }
    assert coerced == {
        "danceability": ("0.521", 0.521, "numeric_string_converted"),
        "tempo": ("108.73", 108.73, "numeric_string_converted"),
        "mood": ("1", 1, "numeric_string_converted"),
    }


def test_mood_and_count_fields_must_be_valid_integers():
    dataset, _ = run([song("a" * 22, mood=2), song("b" * 22, num_sections=0), song("c" * 22, num_segments=7.5)])
    records = by_id(dataset)
    assert records["a" * 22]["mood"] is None
    assert records["b" * 22]["num_sections"] is None
    assert records["c" * 22]["num_segments"] is None


def test_booleans_are_not_accepted_as_numbers():
    dataset, _ = run([song(energy=True)])
    assert dataset[0]["energy"] is None


# --- titles -------------------------------------------------------------------


def test_title_is_trimmed_and_otherwise_untouched():
    dataset, report = run([song("a" * 22, title=" 4 walls  "), song("b" * 22, title="Another Brick")])
    records = by_id(dataset)
    assert records["a" * 22]["title"] == "4 walls"
    assert records["b" * 22]["title"] == "Another Brick"
    (issue,) = issues_for(report, "title")
    assert (issue["issue"], issue["original"]) == ("title_trimmed", " 4 walls  ")


# --- duration correction ------------------------------------------------------


def test_seconds_value_is_corrected_when_segments_corroborate():
    # 158 s over 560 segments is ~282 ms/segment, in line with the other rows.
    dataset, report = run([song(duration_ms=158, num_segments=560)])
    assert dataset[0]["duration_ms"] == 158_000
    (corr,) = report["duration_corrections"]
    assert (corr["original"], corr["value"], corr["issue"]) == (158, 158_000, "duration_correction")
    assert "seconds" in corr["reason"]
    assert report["summary"]["duration_corrections"] == 1


def test_normal_millisecond_durations_are_untouched():
    dataset, report = run([song(duration_ms=200_040)])
    assert dataset[0]["duration_ms"] == 200_040
    assert report["duration_corrections"] == []


def test_small_value_that_segments_do_not_corroborate_is_nulled_not_converted():
    # 158 s over 5 segments would be 31,600 ms/segment: not credible.
    dataset, report = run([song(duration_ms=158, num_segments=5)])
    assert dataset[0]["duration_ms"] is None
    assert report["duration_corrections"] == []
    (issue,) = issues_for(report, "duration_ms")
    assert issue["issue"] == "invalid_value" and issue["original"] == 158


def test_small_value_without_usable_segments_is_not_converted():
    dataset, report = run([song(duration_ms=158, num_segments=None)])
    assert dataset[0]["duration_ms"] is None
    assert issues_for(report, "duration_ms")[0]["reason"].endswith("unverifiable_without_num_segments")


def test_tiny_value_whose_corrected_length_is_implausible_is_nulled():
    dataset, report = run([song(duration_ms=3, num_segments=1)])
    assert dataset[0]["duration_ms"] is None
    assert report["duration_corrections"] == []


def test_non_positive_duration_is_invalid():
    dataset, _ = run([song(duration_ms=0)])
    assert dataset[0]["duration_ms"] is None


# --- duplicate titles ---------------------------------------------------------


def test_same_title_different_ids_are_both_kept_and_flagged():
    dataset, report = run([song("a" * 22, title="Perfect"), song("b" * 22, title="Perfect")])
    assert len(dataset) == 2
    (dup,) = report["duplicate_titles"]
    assert dup["title"] == "Perfect" and dup["ids"] == ["a" * 22, "b" * 22]


# --- determinism and the real data --------------------------------------------


def test_output_is_deterministic_across_separate_processes(tmp_path):
    """Run the real entry point in fresh interpreters with different hash seeds."""
    backend = Path(__file__).resolve().parent.parent
    outputs = []
    for seed in ("0", "1", "12345"):
        out = tmp_path / f"seed{seed}"
        out.mkdir()
        for _, filename in normalizer.SOURCES:
            (out / filename).write_bytes((REAL_DATA / filename).read_bytes())
        subprocess.run(
            [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); from pathlib import Path; "
             "from app import normalizer; normalizer.run(Path(sys.argv[1]))", str(out)],
            cwd=backend,
            env={"PYTHONHASHSEED": seed},
            check=True,
        )
        outputs.append(
            ((out / normalizer.DATASET_FILE).read_bytes(), (out / normalizer.REPORT_FILE).read_bytes())
        )
    assert outputs[0] == outputs[1] == outputs[2]
    assert outputs[0][0] and outputs[0][1]


@pytest.fixture(scope="module")
def real():
    sources = [(name, normalizer.load_columns(REAL_DATA / fn)) for name, fn in normalizer.SOURCES]
    dataset, report = normalize(sources)
    return dataset, report


def test_real_data_has_25_unique_songs_and_keeps_both_perfects(real):
    dataset, report = real
    assert len(dataset) == 25
    perfects = [r for r in dataset if r["title"] == "Perfect"]
    assert {r["id"] for r in perfects} == {"0tgVpDi06FyKpA1z0VMD4v", "7dNsHhGeGU5MV01r06O8gK"}
    assert report["duplicate_titles"][0]["title"] == "Perfect"
    assert perfects[0]["duration_ms"] != perfects[1]["duration_ms"]


def test_real_data_corrects_exactly_the_three_seconds_values(real):
    _, report = real
    corrections = {(c["id"], c["original"], c["value"]) for c in report["duration_corrections"]}
    assert corrections == {
        ("3KkXRkHbMCARz0aVfEt68P", 158, 158_000),
        ("4VqPOruhp5EdPBeR92t6lQ", 270, 270_000),
        ("2QjOHCTQ1Jl3zawyYOpxh6", 356, 356_000),
    }


def test_real_data_single_conflict_is_never_gonna_give_you_up(real):
    dataset, report = real
    (conflict,) = report["conflicts"]
    assert (conflict["id"], conflict["field"]) == ("4uLU6hMCjMI75M1A2tKUQC", "danceability")
    assert (conflict["chosen_value"], conflict["other_value"]) == (0.727, 0.74)
    assert by_id(dataset)["4uLU6hMCjMI75M1A2tKUQC"]["danceability"] == 0.727


def test_real_data_known_invalid_values_are_null(real):
    dataset, _ = real
    records = {r["title"]: r for r in dataset}
    assert records["21 Guns"]["danceability"] is None
    assert records["Another Brick"]["acousticness"] is None
    assert records["Blinding Lights"]["tempo"] is None
    assert records["11:11"]["energy"] is None and records["Yesterday"]["energy"] is None
    assert records["Bohemian Rhapsody"]["acousticness"] is None
    assert records["3AM"]["danceability"] == 0.521 and records["3AM"]["tempo"] == 108.73
    assert "4 walls" in records


def test_run_writes_outputs_without_touching_inputs(tmp_path):
    for _, filename in normalizer.SOURCES:
        (tmp_path / filename).write_bytes((REAL_DATA / filename).read_bytes())
    before = {fn: (tmp_path / fn).read_bytes() for _, fn in normalizer.SOURCES}
    normalizer.run(tmp_path)
    assert {fn: (tmp_path / fn).read_bytes() for _, fn in normalizer.SOURCES} == before
    dataset = json.loads((tmp_path / normalizer.DATASET_FILE).read_text())
    report = json.loads((tmp_path / normalizer.REPORT_FILE).read_text())
    assert len(dataset) == 25 and report["summary"]["unique_ids"] == 25
    first = (tmp_path / normalizer.DATASET_FILE).read_bytes()
    normalizer.run(tmp_path)
    assert (tmp_path / normalizer.DATASET_FILE).read_bytes() == first


# --- duration boundaries --------------------------------------------------------
# Rule: value < 1000, corrected (x1000) within 30 s..30 min, and the corrected
# length implies 100..600 ms per segment.


@pytest.mark.parametrize(
    "value, segments, expected",
    [
        (999, 3330, 999_000),  # largest value still treated as seconds
        (1000, 3333, 1000),  # smallest value left alone
        (1001, 3337, 1001),
        (1000, 1, 1000),  # >= 1000 is never judged against segments
        (30, 100, 30_000),  # exactly 30 s, exactly 300 ms/segment
        (29, 97, None),  # corrected length 29 s is under the 30 s floor
        (30, 300, 30_000),  # exactly 100 ms/segment: lower bound accepted
        (30, 301, None),  # 99.7 ms/segment: just under
        (30, 50, 30_000),  # exactly 600 ms/segment: upper bound accepted
        (30, 49, None),  # 612 ms/segment: just over
        (158, 264, 158_000),  # 598.5 ms/segment
        (158, 263, None),  # 600.8 ms/segment
        (158, 1580, 158_000),  # 100.0 ms/segment
        (158, 1581, None),  # 99.9 ms/segment
        (1, 3, None),
    ],
)
def test_duration_rule_boundaries(value, segments, expected):
    dataset, report = run([song(duration_ms=value, num_segments=segments)])
    assert dataset[0]["duration_ms"] == expected
    corrected = bool(report["duration_corrections"])
    assert corrected == (expected is not None and value < 1000)
    if value >= 1000:
        assert issues_for(report, "duration_ms") == []
    elif expected is None:
        assert issues_for(report, "duration_ms")[0]["issue"] == "invalid_value"


@pytest.mark.parametrize(
    "raw, expected, issue",
    [
        (225_947, 225_947, None),
        (225_947.0, 225_947, None),
        ("225947", 225_947, "type_coercion"),
        (" 225947 ", 225_947, "type_coercion"),
        ("158", 158_000, "duration_correction"),
        (158.0, 158_000, "duration_correction"),
        (158.5, None, "invalid_value"),
        (225_947.5, None, "invalid_value"),
        ("158.5", None, "invalid_value"),
        ("1_0", None, "invalid_value"),
        ("abc", None, "invalid_value"),
        (True, None, "invalid_value"),
        (0, None, "invalid_value"),
        (-158, None, "invalid_value"),
        (float("nan"), None, "invalid_value"),
        (None, None, "missing_value"),
        ("N/A", None, "missing_value"),
        ("", None, "missing_value"),
        (..., None, "missing_value"),
        ([158], None, "invalid_value"),
    ],
)
def test_duration_input_types(raw, expected, issue):
    # 600 segments keeps both 158 s and 225,947 ms comfortably plausible.
    dataset, report = run([song(duration_ms=raw, num_segments=600)])
    assert dataset[0]["duration_ms"] == expected
    found = issues_for(report, "duration_ms")
    assert [i["issue"] for i in found] == ([issue] if issue else [])
    if issue:
        assert found[0]["original"] == (None if raw is ... else raw) or raw != raw  # NaN != NaN


def test_correction_report_has_original_corrected_and_reason():
    _, report = run([song(duration_ms=270, num_segments=1010)])
    (corr,) = report["duration_corrections"]
    assert (corr["original"], corr["value"]) == (270, 270_000)
    assert corr["reason"].startswith("treated_as_seconds")
    assert corr["source"] == "part1" and corr["row"] == "0"


# --- numeric range boundaries -----------------------------------------------------


@pytest.mark.parametrize("field", ["danceability", "energy", "acousticness"])
@pytest.mark.parametrize(
    "value, expected",
    [(0, 0.0), (0.0, 0.0), (1, 1.0), (1.0, 1.0), (0.5, 0.5), (1.0000001, None), (-0.0000001, None), (2, None), (-1, None)],
)
def test_unit_interval_boundaries_are_inclusive(field, value, expected):
    dataset, report = run([song(**{field: value})])
    assert dataset[0][field] == expected
    assert bool(issues_for(report, field, "invalid_value")) == (expected is None)


def test_valence_uses_the_same_unit_interval():
    dataset, _ = run([song("a" * 22)], [song("a" * 22, valence=1.0001), song("b" * 22, valence=1.0)])
    assert by_id(dataset)["a" * 22]["valence"] is None
    assert by_id(dataset)["b" * 22]["valence"] == 1.0


@pytest.mark.parametrize(
    "value, expected",
    [(0, None), (0.0, None), (-1, None), (0.001, 0.001), (400, 400.0), (400.1, None), ("400", 400.0), ("400.1", None)],
)
def test_tempo_boundaries(value, expected):
    dataset, _ = run([song(tempo=value)])
    assert dataset[0]["tempo"] == expected


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("mood", 0, 0), ("mood", 1, 1), ("mood", 2, None), ("mood", -1, None), ("mood", 0.5, None), ("mood", "yes", None),
        ("num_sections", 1, 1), ("num_sections", 0, None), ("num_sections", -3, None), ("num_sections", 8.5, None),
        ("num_segments", 1, 1), ("num_segments", 0, None), ("num_segments", "812", 812),
    ],
)
def test_integer_field_boundaries(field, value, expected):
    dataset, _ = run([song(**{field: value})])
    assert dataset[0][field] == expected


# --- strict numeric strings -----------------------------------------------------


@pytest.mark.parametrize("text", ["1_0", "1_000.5", "1e2", "1E-1", "inf", "Infinity", "-inf", "0x10", "1,5", "1.2.3", "--1", "+", ".", "٣", "１２", "0.5%", "0.5 0.5"])
def test_non_plain_numeric_strings_are_rejected(text):
    dataset, report = run([song(energy=text)])
    assert dataset[0]["energy"] is None
    (issue,) = issues_for(report, "energy")
    assert (issue["issue"], issue["reason"], issue["original"]) == ("invalid_value", "not_a_number", text)


@pytest.mark.parametrize("text, expected", [("0.5", 0.5), (" 0.5 ", 0.5), ("+0.5", 0.5), (".5", 0.5), ("1.", 1.0), ("0", 0.0), ("1", 1.0), ("00.50", 0.5)])
def test_plain_numeric_strings_are_accepted(text, expected):
    dataset, report = run([song(energy=text)])
    assert dataset[0]["energy"] == expected
    assert issues_for(report, "energy")[0]["issue"] == "type_coercion"


# --- ids: whitespace and within-file duplicates -------------------------------------


def test_id_whitespace_is_trimmed_reported_and_merges_across_sources():
    dataset, report = run([song(" " + "a" * 22 + "\t")], [song("a" * 22, valence=0.4)])
    assert [r["id"] for r in dataset] == ["a" * 22]
    assert dataset[0]["sources"] == ["part1", "part2"]
    (issue,) = issues_for(report, "id")
    assert issue["issue"] == "id_trimmed" and issue["original"] == " " + "a" * 22 + "\t"
    assert report["summary"]["ids_in_multiple_sources"] == 1


def test_untrimmed_id_has_no_id_issue_and_blank_id_is_dropped():
    dataset, report = run([song("a" * 22), song("   ")])
    assert issues_for(report, "id") == []
    assert len(dataset) == 1 and report["dropped_records"][0]["reason"] == "missing_or_empty_id"


def test_within_file_duplicate_id_is_one_source_not_multiple():
    dataset, report = normalize([("part1", columns(song(title="First"), song(title="Second"), song("b" * 22)))])
    assert len(dataset) == 2
    assert dataset[0]["title"] == "First" and dataset[0]["sources"] == ["part1"]
    assert report["summary"]["ids_in_multiple_sources"] == 0
    assert report["summary"]["duplicate_rows_within_a_source"] == 1
    (conflict,) = report["conflicts"]
    assert (conflict["chosen_source"], conflict["other_source"]) == ("part1", "part1")
    assert (conflict["chosen_row"], conflict["other_row"]) == ("0", "1")


def test_within_file_duplicate_plus_other_file_lists_each_source_once():
    sources = [
        ("part1", columns(song(), song())),
        ("part2", columns(song(valence=0.3))),
    ]
    dataset, report = normalize(sources)
    assert dataset[0]["sources"] == ["part1", "part2"]
    assert report["summary"]["ids_in_multiple_sources"] == 1
    assert report["summary"]["duplicate_rows_within_a_source"] == 1


def test_identical_within_file_duplicate_is_counted_but_not_a_conflict():
    _, report = normalize([("part1", columns(song(), song()))])
    assert report["summary"]["duplicate_rows_within_a_source"] == 1
    assert report["conflicts"] == []


# --- fill reporting ---------------------------------------------------------------


def test_fill_preserves_invalid_original_and_explains_why():
    dataset, report = run([song(danceability=1.42)], [song(danceability=0.6)])
    assert dataset[0]["danceability"] == 0.6
    (fill,) = report["filled_from_other_source"]
    assert fill["primary_status"] == "invalid_value"
    assert fill["primary_original"] == 1.42
    assert fill["primary_reason"] == "out_of_range_0_to_1"
    assert (fill["filled_from"], fill["value"], fill["original"]) == ("part2", 0.6, 0.6)
    assert "invalid" in fill["reason"] and "out_of_range_0_to_1" in fill["reason"]
    assert (fill["primary_row"], fill["filled_from_row"]) == ("0", "0")
    # The nulling itself is still reported, and it is not a conflict.
    assert issues_for(report, "danceability", "invalid_value")[0]["original"] == 1.42
    assert report["conflicts"] == []


@pytest.mark.parametrize(
    "raw, reason",
    [(None, "null"), ("N/A", "placeholder_string"), ("", "empty_string"), (..., "missing_key")],
)
def test_fill_for_missing_value_reports_how_it_was_missing(raw, reason):
    _, report = run([song(energy=raw)], [song(energy=0.7)])
    (fill,) = report["filled_from_other_source"]
    assert fill["primary_status"] == "missing_value"
    assert fill["primary_reason"] == reason
    assert fill["primary_original"] == (None if raw is ... else raw)
    assert "missing" in fill["reason"] and reason in fill["reason"]


def test_fill_for_unprovided_column_says_column_not_provided():
    _, report = run([song()], [song(valence=0.4)])
    (fill,) = report["filled_from_other_source"]
    assert fill["field"] == "valence" and fill["primary_status"] == "column_not_provided"
    assert fill["primary_reason"] is None and fill["primary_original"] is None
    assert "does not provide this column" in fill["reason"]
    assert "no usable value" not in fill["reason"]


def test_fill_keeps_part1_invalid_original_when_part2_value_differs_widely():
    dataset, report = run([song(tempo=0)], [song(tempo=130.0)])
    assert dataset[0]["tempo"] == 130.0
    (fill,) = report["filled_from_other_source"]
    assert (fill["primary_original"], fill["primary_reason"]) == (0, "tempo_not_positive")


def test_fill_for_corrected_duration_in_part2():
    dataset, report = run([song(duration_ms=None)], [song(duration_ms=200, num_segments=800)])
    assert dataset[0]["duration_ms"] == 200_000
    (fill,) = report["filled_from_other_source"]
    assert fill["field"] == "duration_ms" and fill["original"] == 200 and fill["value"] == 200_000


# --- report rules documentation -------------------------------------------------


def test_report_documents_fill_and_null_like_rules():
    _, report = run([song()])
    rules = report["rules"]
    assert "never overrides a valid earlier value" in rules["fill_rule"]
    assert "conflict_rule" in rules and rules["numeric_string_format"] == normalizer.NUMERIC_STRING.pattern
    assert rules["null_like_values"]["placeholder_strings"] == sorted(s for s in normalizer.NULL_STRINGS if s)


def test_every_documented_placeholder_really_normalizes_to_null():
    _, report = run([song()])
    placeholders = report["rules"]["null_like_values"]["placeholder_strings"]
    assert placeholders  # documentation is not empty
    for text in placeholders + [p.upper() for p in placeholders] + [f"  {p} " for p in placeholders]:
        dataset, _ = run([song(energy=text)])
        assert dataset[0]["energy"] is None, text


# --- duplicate titles: case and Unicode ---------------------------------------------


def test_duplicate_titles_ignore_case_whitespace_and_unicode_form():
    nfc, nfd = "Caf\u00e9", "Cafe\u0301"
    dataset, report = run(
        [
            song("a" * 22, title="Perfect"),
            song("b" * 22, title="PERFECT"),
            song("c" * 22, title="perfect"),
            song("d" * 22, title=nfc),
            song("e" * 22, title=nfd),
            song("f" * 22, title="Two  Words"),
            song("g" * 22, title="two words"),
        ]
    )
    groups = {tuple(d["ids"]): d for d in report["duplicate_titles"]}
    assert set(groups) == {("a" * 22, "b" * 22, "c" * 22), ("d" * 22, "e" * 22), ("f" * 22, "g" * 22)}
    assert groups[("a" * 22, "b" * 22, "c" * 22)]["titles"] == ["Perfect", "PERFECT", "perfect"]
    assert len(dataset) == 7  # nothing merged or dropped
    # Stored titles are not rewritten to match each other.
    assert {r["title"] for r in dataset} >= {nfc, nfd, "PERFECT", "perfect"}


def test_duplicate_title_check_does_not_fold_diacritics():
    _, report = run([song("a" * 22, title="Naïve"), song("b" * 22, title="Naive")])
    assert report["duplicate_titles"] == []


def test_distinct_titles_are_not_flagged():
    _, report = run([song("a" * 22, title="21"), song("b" * 22, title="21 Guns")])
    assert report["duplicate_titles"] == []
