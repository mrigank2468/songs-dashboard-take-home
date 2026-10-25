"""Title search: GET /songs?title=...  Order of operations is filter, sort, paginate."""

import unicodedata

import pytest
from helpers import client_with, ids, make_song

from app.search import filter_by_title


def songs_titled(*titles) -> list[dict]:
    songs = []
    for n, title in enumerate(titles):
        song = make_song(n)
        song["title"] = title
        songs.append(song)
    return songs


def search(client, title=None, **params):
    if title is not None:
        params["title"] = title
    response = client.get("/songs", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def titles_client(tmp_path):
    songs = songs_titled(
        "Perfect",  # id000
        "perfect",  # id001
        "  PERFECT ",  # id002
        "Perfect Day",  # id003: contains the word but is a different title
        "Never  Gonna   Give You Up",  # id004
        "Café del Mar",  # id005
        None,  # id006
        "21",  # id007
        "21 Guns",  # id008
    )
    with client_with(tmp_path, songs) as c:
        yield c


# --- matching rules -----------------------------------------------------------------


@pytest.mark.parametrize("query", ["Perfect", "perfect", "PERFECT", "pErFeCt", "  perfect  ", "\tPerfect\n"])
def test_match_ignores_case_and_surrounding_whitespace(titles_client, query):
    assert ids(search(titles_client, query)) == ["id000", "id001", "id002", "id003"]


@pytest.mark.parametrize(
    "query",
    ["never gonna give you up", "Never Gonna Give You Up", "NEVER   GONNA\tGIVE  YOU   UP", " never  gonna give you up "],
)
def test_match_ignores_differences_in_runs_of_internal_whitespace(titles_client, query):
    # The stored title has doubled and tripled spaces; the query may have any spacing.
    assert ids(search(titles_client, query)) == ["id004"]


def test_all_matches_are_returned_because_titles_are_not_unique(titles_client):
    body = search(titles_client, "perfect")
    assert body["total"] == 4
    assert len({s["id"] for s in body["songs"]}) == 4
    assert {s["title"] for s in body["songs"]} == {"Perfect", "perfect", "  PERFECT ", "Perfect Day"}  # titles are not rewritten


def test_match_is_a_substring_search(titles_client):
    assert ids(search(titles_client, "Perf")) == ["id000", "id001", "id002", "id003"]
    assert ids(search(titles_client, "day")) == ["id003"]
    assert ids(search(titles_client, "Perfect Day")) == ["id003"]
    assert ids(search(titles_client, "21")) == ["id007", "id008"]
    assert ids(search(titles_client, "21 guns")) == ["id008"]


def test_unicode_forms_match_but_diacritics_are_not_folded(titles_client):
    nfd = unicodedata.normalize("NFD", "Café del Mar")
    assert nfd != "Café del Mar"
    assert ids(search(titles_client, nfd)) == ["id005"]
    assert ids(search(titles_client, "CAFÉ DEL MAR")) == ["id005"]
    assert ids(search(titles_client, "Cafe del Mar")) == []


def test_songs_without_a_title_never_match_a_search(titles_client):
    for query in ("None", "null", "none", "id006"):
        assert "id006" not in ids(search(titles_client, query))


# --- empty or whitespace-only search ---------------------------------------------------


@pytest.mark.parametrize("query", ["", " ", "   ", "\t", "\n", " \t \n "])
def test_blank_search_means_no_filter(titles_client, query):
    blank = search(titles_client, query)
    assert blank == search(titles_client)  # identical to omitting the parameter
    assert blank["total"] == 9  # including the song with no title


def test_blank_search_keeps_sorting_and_pagination(titles_client):
    assert search(titles_client, "  ", sort_by="id", order="desc", size=3)["songs"][0]["id"] == "id008"


# --- no results and metadata -------------------------------------------------------------


def test_no_match_returns_an_empty_page_with_correct_metadata(titles_client):
    assert search(titles_client, "no such song") == {"songs": [], "page": 1, "size": 10, "total": 0, "total_pages": 0}


def test_no_match_keeps_the_requested_page_and_size(titles_client):
    body = search(titles_client, "zzz", page=3, size=7, sort_by="tempo", order="desc")
    assert body == {"songs": [], "page": 3, "size": 7, "total": 0, "total_pages": 0}


def test_total_and_total_pages_describe_the_filtered_set(tmp_path):
    songs = songs_titled(*(["Dup", "Other", "Dup"][n % 3] if n % 3 != 1 else "Other" for n in range(30)))
    matches = [s["id"] for s in songs if s["title"] == "Dup"]
    assert len(matches) == 20
    with client_with(tmp_path, songs) as c:
        first = search(c, "dup", size=8)
        assert (first["total"], first["total_pages"], first["page"], first["size"]) == (20, 3, 1, 8)
        assert ids(search(c, "dup", size=8, page=3)) == matches[16:]
        past = search(c, "dup", size=8, page=4)
        assert past["songs"] == [] and (past["total"], past["total_pages"]) == (20, 3)


# --- search + sorting + pagination ---------------------------------------------------------


def scattered():
    """40 songs; every 3rd is titled 'Match' (varying case and spacing), tempos shuffled."""
    songs = []
    for n in range(40):
        song = make_song(n)
        song["title"] = ["Match", "  match", "MATCH  "][(n // 3) % 3] if n % 3 == 0 else f"Other {n}"
        song["tempo"] = 60.0 + (n * 7) % 40
        song["energy"] = None if n % 4 == 0 else round(0.01 * ((n * 13) % 40), 2)
        songs.append(song)
    return songs


def test_pipeline_is_filter_then_sort_then_paginate(tmp_path):
    songs = scattered()
    matching = [s for s in songs if s["title"].strip().lower() == "match"]
    assert len(matching) == 14
    expected = [s["id"] for s in sorted(matching, key=lambda s: (-s["tempo"], s["id"]))]
    with client_with(tmp_path, songs) as c:
        pages = [search(c, "MATCH", sort_by="tempo", order="desc", size=5, page=p) for p in (1, 2, 3)]
        assert [ids(p) for p in pages] == [expected[:5], expected[5:10], expected[10:]]
        assert all((p["total"], p["total_pages"]) == (14, 3) for p in pages)

        # Guards: the wrong orders of operations would give different answers here.
        sort_all_then_page_then_filter = [
            s["id"]
            for s in sorted(songs, key=lambda s: (-s["tempo"], s["id"]))[:5]
            if s["title"].strip().lower() == "match"
        ]
        assert ids(pages[0]) != sort_all_then_page_then_filter
        filter_page_then_sort = [s["id"] for s in sorted(matching[:5], key=lambda s: (-s["tempo"], s["id"]))]
        assert ids(pages[0]) != filter_page_then_sort


def test_nulls_stay_last_and_ties_stay_deterministic_within_a_search(tmp_path):
    songs = scattered()
    matching = [s for s in songs if s["title"].strip().lower() == "match"]
    present = sorted((s for s in matching if s["energy"] is not None), key=lambda s: (s["energy"], s["id"]))
    missing = sorted((s for s in matching if s["energy"] is None), key=lambda s: s["id"])
    assert present and missing
    with client_with(tmp_path, songs) as c:
        asc = [s["id"] for s in present] + [s["id"] for s in missing]
        desc = [s["id"] for s in sorted(present, key=lambda s: (-s["energy"], s["id"]))] + [s["id"] for s in missing]
        assert ids(search(c, "match", sort_by="energy", size=100)) == asc
        assert ids(search(c, "match", sort_by="energy", order="desc", size=100)) == desc
        # a tie-heavy field: mood is 0/1, so ties are broken by id in both directions
        by_mood = [s["id"] for s in sorted(matching, key=lambda s: (s["mood"], s["id"]))]
        assert ids(search(c, "match", sort_by="mood", size=100)) == by_mood
        assert search(c, "match", sort_by="mood", size=5) == search(c, "match", sort_by="mood", size=5)


def test_search_without_sort_keeps_dataset_order(tmp_path):
    songs = scattered()
    expected = [s["id"] for s in songs if s["title"].strip().lower() == "match"]
    with client_with(tmp_path, songs) as c:
        assert ids(search(c, "match", size=100)) == expected


def test_search_on_an_empty_dataset(tmp_path):
    with client_with(tmp_path, []) as c:
        assert search(c, "anything") == {"songs": [], "page": 1, "size": 10, "total": 0, "total_pages": 0}
        assert search(c) == search(c, "anything")


def test_invalid_pagination_and_sort_are_still_rejected_with_a_search(titles_client):
    detail = titles_client.get("/songs", params={"title": "x", "page": 0, "sort_by": "bogus"}).json()["detail"]
    assert {e["loc"][-1] for e in detail} == {"page", "sort_by"}


# --- the filter function ---------------------------------------------------------------------


def test_filter_by_title_does_not_modify_or_copy_for_no_filter():
    songs = songs_titled("A", "b")
    assert filter_by_title(songs, None) is songs
    assert filter_by_title(songs, "  ") is songs
    assert [s["title"] for s in filter_by_title(songs, " B ")] == ["b"]
    assert [s["title"] for s in songs] == ["A", "b"]


# --- the real dataset ---------------------------------------------------------------------------


def test_real_dataset_duplicate_titles_are_all_returned(real_client):
    body = real_client.get("/songs", params={"title": "  perfect "}).json()
    assert body["total"] == 2 and len({s["id"] for s in body["songs"]}) == 2
    assert {s["title"] for s in body["songs"]} == {"Perfect"}


def test_real_dataset_whitespace_padded_title_was_normalized_and_is_searchable(real_client):
    # The export stored " 4 walls  "; the normalizer trimmed it.
    body = real_client.get("/songs", params={"title": "4  WALLS"}).json()
    assert [s["title"] for s in body["songs"]] == ["4 walls"]


def test_real_dataset_partial_title_matches_longer_titles(real_client):
    titles = [s["title"] for s in real_client.get("/songs", params={"title": "21", "size": 100}).json()["songs"]]
    assert "21" in titles and all("21" in t for t in titles)
    assert [s["title"] for s in real_client.get("/songs", params={"title": "Naïve"}).json()["songs"]] == ["Naïve"]


def test_real_dataset_search_sort_paginate(real_client):
    body = real_client.get("/songs", params={"title": "perfect", "sort_by": "duration_ms", "order": "desc", "size": 1, "page": 2}).json()
    assert (body["total"], body["total_pages"], body["page"]) == (2, 2, 2)
    assert [s["duration_ms"] for s in body["songs"]] == [263_400]  # the shorter "Perfect" is last in descending order
