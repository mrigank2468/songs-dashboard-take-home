import json
import math

import pytest
from fastapi.testclient import TestClient
from helpers import SONG_FIELDS, client_for, client_with, ids, make_song, public

from app.data import DATA_FILE, load_songs
from app.main import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, create_app


@pytest.fixture
def client(tmp_path):
    """25 synthetic songs: 3 pages of 10, the last holding 5."""
    with client_for(tmp_path, 25) as c:
        yield c


# --- default response and metadata --------------------------------------------------


def test_default_is_page_1_with_10_songs(client):
    response = client.get("/songs")
    assert response.status_code == 200
    body = response.json()
    assert (body["page"], body["size"]) == (1, DEFAULT_PAGE_SIZE) == (1, 10)
    assert ids(body) == [f"id{n:03d}" for n in range(10)]


def test_response_structure_and_metadata(client):
    body = client.get("/songs").json()
    assert set(body) == {"songs", "page", "size", "total", "total_pages"}
    assert body["total"] == 25
    assert body["total_pages"] == 3


def test_each_song_has_the_full_schema_and_keeps_nulls(client):
    first, second = client.get("/songs?size=2").json()["songs"]
    assert set(first) == SONG_FIELDS
    assert first == public(make_song(0))
    assert second["energy"] is None and second["valence"] is None


def test_sources_is_in_the_dataset_but_not_in_the_response(client):
    assert "sources" in make_song(0)  # the test data carries it, like the real file
    songs = client.get("/songs?size=100").json()["songs"]
    assert songs and all("sources" not in s for s in songs)


def test_total_pages_rounds_up_and_is_exact_for_multiples(tmp_path):
    for count, size, expected in [(20, 10, 2), (21, 10, 3), (1, 10, 1), (25, 25, 1), (25, 100, 1), (25, 1, 25)]:
        with client_for(tmp_path, count) as c:
            body = c.get(f"/songs?size={size}").json()
            assert body["total_pages"] == expected == math.ceil(count / size)


# --- custom pagination, first and last pages -----------------------------------------


def test_custom_page_and_size(client):
    body = client.get("/songs?page=2&size=7").json()
    assert (body["page"], body["size"], body["total"], body["total_pages"]) == (2, 7, 25, 4)
    assert ids(body) == [f"id{n:03d}" for n in range(7, 14)]


def test_first_page(client):
    body = client.get("/songs?page=1&size=10").json()
    assert ids(body)[0] == "id000" and len(body["songs"]) == 10


def test_last_page_holds_the_remainder(client):
    body = client.get("/songs?page=3&size=10").json()
    assert ids(body) == [f"id{n:03d}" for n in range(20, 25)]
    assert body["page"] == body["total_pages"] == 3


def test_last_page_that_is_exactly_full(tmp_path):
    with client_for(tmp_path, 20) as c:
        body = c.get("/songs?page=2&size=10").json()
        assert len(body["songs"]) == 10 and ids(body)[-1] == "id019"
        assert c.get("/songs?page=3&size=10").json()["songs"] == []


def test_size_larger_than_dataset_returns_everything_on_one_page(client):
    body = client.get(f"/songs?size={MAX_PAGE_SIZE}").json()
    assert len(body["songs"]) == 25 and body["total_pages"] == 1


def test_pages_cover_the_whole_dataset_in_order_without_repeats(client):
    collected = []
    for page in range(1, 4):
        collected += ids(client.get(f"/songs?page={page}&size=10").json())
    assert collected == [f"id{n:03d}" for n in range(25)]


# --- empty results --------------------------------------------------------------------


def test_page_past_the_end_is_an_empty_200_with_unchanged_metadata(client):
    response = client.get("/songs?page=4&size=10")
    assert response.status_code == 200
    assert response.json() == {"songs": [], "page": 4, "size": 10, "total": 25, "total_pages": 3}


def test_very_large_page_number_is_just_empty(client):
    response = client.get(f"/songs?page={10**18}")
    assert response.status_code == 200 and response.json()["songs"] == []


def test_empty_dataset(tmp_path):
    with client_for(tmp_path, 0) as c:
        response = c.get("/songs")
        assert response.status_code == 200
        assert response.json() == {"songs": [], "page": 1, "size": 10, "total": 0, "total_pages": 0}


# --- validation -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, bad_param",
    [
        ("page=0", "page"),
        ("page=-1", "page"),
        ("page=abc", "page"),
        ("page=1.5", "page"),
        ("page=", "page"),
        ("size=0", "size"),
        ("size=-5", "size"),
        (f"size={MAX_PAGE_SIZE + 1}", "size"),
        ("size=abc", "size"),
        ("size=2.5", "size"),
        ("size=", "size"),
        ("page=0&size=0", "page"),
    ],
)
def test_invalid_pagination_is_rejected_with_422(client, query, bad_param):
    response = client.get(f"/songs?{query}")
    assert response.status_code == 422
    assert bad_param in [e["loc"][-1] for e in response.json()["detail"]]


def test_both_invalid_parameters_are_reported(client):
    detail = client.get("/songs?page=0&size=0").json()["detail"]
    assert {e["loc"][-1] for e in detail} == {"page", "size"}


def test_size_limits_are_inclusive(client):
    assert client.get("/songs?size=1").status_code == 200
    assert client.get(f"/songs?size={MAX_PAGE_SIZE}").status_code == 200


def test_unknown_route_and_wrong_method(client):
    assert client.get("/nope").status_code == 404
    assert client.post("/songs").status_code == 405


# --- data loading ---------------------------------------------------------------------


def test_missing_data_file_stops_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(tmp_path / "missing.json")):
            pass


@pytest.mark.parametrize("content", ['{"a": 1}', "[1, 2]", "not json"])
def test_malformed_data_file_stops_startup(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValueError):  # json.JSONDecodeError is a ValueError
        with TestClient(create_app(path)):
            pass


def test_load_songs_does_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    expected = load_songs()
    monkeypatch.chdir(tmp_path)
    assert load_songs() == expected
    assert DATA_FILE.is_absolute()
    with TestClient(create_app()) as c:  # default path, from an unrelated cwd
        assert c.get("/songs").json()["total"] == len(expected)


def test_requests_do_not_modify_the_data_file(tmp_path):
    path = tmp_path / "songs.json"
    path.write_text(json.dumps([make_song(n) for n in range(25)]))
    before = path.read_bytes()
    with TestClient(create_app(path)) as c:
        for query in ["", "?page=2&size=5", "?page=99", "?page=0"]:
            c.get(f"/songs{query}")
    assert path.read_bytes() == before


# --- the real normalized dataset ------------------------------------------------------


def test_real_dataset_is_fully_paginated(real_client):
    expected = [s["id"] for s in json.loads(DATA_FILE.read_text())]
    assert len(expected) == 25
    first = real_client.get("/songs").json()
    assert (first["total"], first["total_pages"], first["page"], first["size"]) == (25, 3, 1, 10)
    collected = []
    for page in range(1, first["total_pages"] + 1):
        collected += ids(real_client.get(f"/songs?page={page}").json())
    assert collected == expected
    assert len(real_client.get("/songs?page=3").json()["songs"]) == 5


def test_real_dataset_songs_match_the_file_exactly(real_client):
    on_disk = json.loads(DATA_FILE.read_text())
    assert all("sources" in s for s in on_disk)  # still kept in the normalized file
    served = real_client.get("/songs?size=100").json()["songs"]
    assert served == [public(s) for s in on_disk]
    assert all(set(s) == SONG_FIELDS for s in served)


# --- sorting ----------------------------------------------------------------------------
# Expected orders below are computed with plain `sorted` in the tests, independently
# of app.sorting, from datasets whose file order is deliberately not sorted.


def shuffled_songs() -> list[dict]:
    """25 songs whose tempo, duration and title orders all differ from file order."""
    songs = []
    for n in range(25):
        song = make_song(n)
        rank = (n * 7) % 25  # a permutation of 0..24, since gcd(7, 25) == 1
        song["tempo"] = 60.0 + rank * 3
        song["duration_ms"] = 300_000 - ((n * 11) % 25) * 1_000
        song["title"] = f"T{rank:02d}"
        songs.append(song)
    return songs


@pytest.fixture
def shuffled(tmp_path):
    songs = shuffled_songs()
    with client_with(tmp_path, songs) as c:
        yield c, songs


def songs_with(field: str, values: list, id_order: list[int] | None = None) -> list[dict]:
    """One song per value, with ids id000.. assigned in `id_order` (default: in sequence)."""
    songs = []
    for position, value in enumerate(values):
        song = make_song(id_order[position] if id_order else position)
        song[field] = value
        songs.append(song)
    return songs


def sorted_ids(client, **params) -> list[str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    response = client.get(f"/songs?{query}")
    assert response.status_code == 200, response.text
    return ids(response.json())


# numeric ------------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["tempo", "duration_ms"])
def test_numeric_sort_ascending_and_descending(shuffled, field):
    client, songs = shuffled
    expected = [s["id"] for s in sorted(songs, key=lambda s: s[field])]
    assert expected != [s["id"] for s in songs]  # the data really is out of order
    assert sorted_ids(client, sort_by=field, size=100) == expected
    assert sorted_ids(client, sort_by=field, order="asc", size=100) == expected
    assert sorted_ids(client, sort_by=field, order="desc", size=100) == expected[::-1]


def test_float_and_integer_fields_both_sort_numerically_not_as_text(tmp_path):
    # As text "100" < "20" < "3"; numerically it is 3 < 20 < 100.
    with client_with(tmp_path, songs_with("duration_ms", [100, 20, 3])) as c:
        assert sorted_ids(c, sort_by="duration_ms") == ["id002", "id001", "id000"]
    with client_with(tmp_path, songs_with("danceability", [0.5, 0.25, 0.125])) as c:
        assert sorted_ids(c, sort_by="danceability") == ["id002", "id001", "id000"]


# strings ------------------------------------------------------------------------------


def test_title_sorts_alphabetically_ignoring_case(tmp_path):
    titles = ["banana", "Cherry", "apple", "Banana2", "Apple2"]
    with client_with(tmp_path, songs_with("title", titles)) as c:
        expected = sorted(range(5), key=lambda i: titles[i].casefold())
        assert sorted_ids(c, sort_by="title") == [f"id{i:03d}" for i in expected]
        assert [titles[i] for i in expected] == ["apple", "Apple2", "banana", "Banana2", "Cherry"]
        assert sorted_ids(c, sort_by="title", order="desc") == [f"id{i:03d}" for i in expected][::-1]


def test_titles_equal_ignoring_case_fall_back_to_id(tmp_path):
    songs = songs_with("title", ["Perfect", "perfect", "PERFECT"], id_order=[2, 0, 1])
    with client_with(tmp_path, songs) as c:
        assert sorted_ids(c, sort_by="title") == ["id000", "id001", "id002"]


def test_id_sort_is_case_sensitive_code_point_order(tmp_path):
    songs = songs_with("id", ["b" * 22, "B" * 22, "a" * 22, "A" * 22])
    with client_with(tmp_path, songs) as c:
        assert sorted_ids(c, sort_by="id") == ["A" * 22, "B" * 22, "a" * 22, "b" * 22]


# nulls --------------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_nulls_sort_last_in_both_directions(tmp_path, order):
    values = [0.5, None, 0.9, None, 0.1, 0.7]
    with client_with(tmp_path, songs_with("energy", values)) as c:
        got = sorted_ids(c, sort_by="energy", order=order)
    present = sorted((v, f"id{i:03d}") for i, v in enumerate(values) if v is not None)
    present_ids = [i for _, i in present]
    assert got == (present_ids if order == "asc" else present_ids[::-1]) + ["id001", "id003"]


def test_nulls_do_not_break_sorting_on_any_page(tmp_path):
    values = [0.5, None, 0.9, None, 0.1, 0.7]
    with client_with(tmp_path, songs_with("energy", values)) as c:
        pages = [sorted_ids(c, sort_by="energy", size=4, page=p) for p in (1, 2)]
    assert pages == [["id004", "id000", "id005", "id002"], ["id001", "id003"]]


def test_all_null_column_and_null_titles_sort_without_error(tmp_path):
    with client_with(tmp_path, songs_with("valence", [None, None, None])) as c:
        assert sorted_ids(c, sort_by="valence", order="desc") == ["id000", "id001", "id002"]
    with client_with(tmp_path, songs_with("title", ["b", None, "a"])) as c:
        assert sorted_ids(c, sort_by="title") == ["id002", "id000", "id001"]


def test_null_energy_in_real_data_comes_last(real_client):
    for order in ("asc", "desc"):
        body = real_client.get(f"/songs?sort_by=energy&order={order}&size=100").json()
        energies = [s["energy"] for s in body["songs"]]
        assert energies[-2:] == [None, None] and None not in energies[:-2]
        present = energies[:-2]
        assert present == sorted(present, reverse=(order == "desc"))


# invalid values -----------------------------------------------------------------------


@pytest.mark.parametrize("value", ["bogus", "sources", "TEMPO", "Tempo", "tempo%20", "", "duration", "id,title"])
def test_invalid_sort_by_is_422_and_lists_valid_fields(client, value):
    response = client.get(f"/songs?sort_by={value}")
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["query", "sort_by"]
    assert "'tempo'" in error["msg"] and "'valence'" in error["msg"]


@pytest.mark.parametrize("value", ["up", "ASC", "Desc", "descending", "ascending", "1", ""])
def test_invalid_order_is_422_and_lists_valid_directions(client, value):
    response = client.get(f"/songs?sort_by=tempo&order={value}")
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["query", "order"]
    assert "'asc' or 'desc'" in error["msg"]


def test_invalid_sort_and_page_parameters_are_all_reported(client):
    detail = client.get("/songs?sort_by=x&order=y&page=0").json()["detail"]
    assert {e["loc"][-1] for e in detail} == {"sort_by", "order", "page"}


def test_every_exposed_field_is_sortable_and_sources_is_not(client):
    for field in SONG_FIELDS:
        assert client.get(f"/songs?sort_by={field}").status_code == 200, field
    assert client.get("/songs?sort_by=sources").status_code == 422


def test_order_without_sort_by_keeps_the_dataset_order(shuffled):
    client, songs = shuffled
    file_order = [s["id"] for s in songs][:10]
    assert sorted_ids(client) == file_order
    assert sorted_ids(client, order="desc") == file_order
    assert sorted_ids(client, order="asc") == file_order


# sorting combined with pagination -----------------------------------------------------


def test_sorting_is_global_not_within_the_requested_page(shuffled):
    """Fails if the page is cut first and only then sorted."""
    client, songs = shuffled
    global_order = [s["id"] for s in sorted(songs, key=lambda s: s["tempo"])]
    page_then_sort = [s["id"] for s in sorted(songs[:5], key=lambda s: s["tempo"])]
    assert global_order[:5] != page_then_sort  # the two approaches really differ here

    assert sorted_ids(client, sort_by="tempo", size=5, page=1) == global_order[:5]
    assert sorted_ids(client, sort_by="tempo", size=5, page=3) == global_order[10:15]
    # The highest tempo overall lives far past the first page of the file, so it can
    # only be returned first if the whole dataset was sorted before paging.
    highest = max(songs, key=lambda s: s["tempo"])["id"]
    assert [s["id"] for s in songs].index(highest) >= 5
    assert sorted_ids(client, sort_by="tempo", order="desc", size=1) == [highest]


def test_descending_pages_come_from_the_end_of_the_whole_dataset(shuffled):
    client, songs = shuffled
    desc = [s["id"] for s in sorted(songs, key=lambda s: s["tempo"], reverse=True)]
    assert sorted_ids(client, sort_by="tempo", order="desc", size=5, page=1) == desc[:5]
    assert sorted_ids(client, sort_by="tempo", order="desc", size=5, page=5) == desc[20:25]


def test_sorted_pages_partition_the_dataset_with_no_gaps_or_repeats(shuffled):
    client, songs = shuffled
    for order in ("asc", "desc"):
        collected = []
        for page in range(1, 5):
            collected += sorted_ids(client, sort_by="duration_ms", order=order, size=7, page=page)
        assert len(collected) == 25 and set(collected) == {s["id"] for s in songs}
        assert collected == sorted_ids(client, sort_by="duration_ms", order=order, size=100)


def test_sorting_keeps_pagination_metadata_and_response_format(shuffled):
    client, _ = shuffled
    plain = client.get("/songs?page=2&size=7").json()
    sorted_body = client.get("/songs?page=2&size=7&sort_by=tempo&order=desc").json()
    assert set(sorted_body) == set(plain) == {"songs", "page", "size", "total", "total_pages"}
    for key in ("page", "size", "total", "total_pages"):
        assert sorted_body[key] == plain[key]
    assert all(set(s) == SONG_FIELDS for s in sorted_body["songs"])


def test_page_past_the_end_is_still_empty_when_sorted(shuffled):
    client, _ = shuffled
    body = client.get("/songs?sort_by=tempo&page=9&size=10").json()
    assert body == {"songs": [], "page": 9, "size": 10, "total": 25, "total_pages": 3}


def test_sorting_does_not_change_the_default_order_or_the_data_file(tmp_path):
    songs = shuffled_songs()
    path = tmp_path / "songs.json"
    path.write_text(json.dumps(songs))
    before = path.read_bytes()
    with TestClient(create_app(path)) as c:
        default_before = ids(c.get("/songs?size=100").json())
        c.get("/songs?sort_by=tempo&order=desc")
        c.get("/songs?sort_by=title")
        assert ids(c.get("/songs?size=100").json()) == default_before == [s["id"] for s in songs]
    assert path.read_bytes() == before


# ties and determinism -----------------------------------------------------------------


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_ties_are_broken_by_id_ascending_in_both_directions(tmp_path, order):
    moods = [1, 0, 1, 0, 1, 0, 1, 0]
    id_order = [5, 2, 7, 0, 3, 6, 1, 4]  # file order is not id order
    with client_with(tmp_path, songs_with("mood", moods, id_order)) as c:
        got = sorted_ids(c, sort_by="mood", order=order)
    zero = sorted(f"id{i:03d}" for i, m in zip(id_order, moods) if m == 0)
    one = sorted(f"id{i:03d}" for i, m in zip(id_order, moods) if m == 1)
    assert got == (zero + one if order == "asc" else one + zero)


def test_result_does_not_depend_on_the_order_of_the_file(tmp_path):
    # Lots of ties (mood, num_sections) and nulls (energy): the worst case for stability.
    songs = [make_song(n) for n in range(25)]
    for n, song in enumerate(songs):
        song["num_sections"] = 3 + n % 3
    reordered = songs[::-1][5:] + songs[::-1][:5]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with client_with(tmp_path / "a", songs) as a, client_with(tmp_path / "b", reordered) as b:
        for field in ("mood", "num_sections", "energy", "valence", "title"):
            for order in ("asc", "desc"):
                assert sorted_ids(a, sort_by=field, order=order, size=100) == sorted_ids(
                    b, sort_by=field, order=order, size=100
                ), (field, order)


def test_repeated_requests_return_identical_responses(real_client):
    for query in ("sort_by=mood", "sort_by=mood&order=desc&page=2&size=5", "sort_by=valence&order=desc"):
        first = real_client.get(f"/songs?{query}").json()
        assert all(real_client.get(f"/songs?{query}").json() == first for _ in range(5))


def test_ties_do_not_split_across_pages(tmp_path):
    moods = [n % 2 for n in range(10)]
    with client_with(tmp_path, songs_with("mood", moods)) as c:
        pages = [sorted_ids(c, sort_by="mood", size=3, page=p) for p in (1, 2, 3, 4)]
    assert sum(pages, []) == ["id000", "id002", "id004", "id006", "id008", "id001", "id003", "id005", "id007", "id009"]


# the real dataset ---------------------------------------------------------------------


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("field", sorted(SONG_FIELDS))
def test_real_dataset_sorts_correctly_by_every_field(real_client, field, order):
    on_disk = json.loads(DATA_FILE.read_text())
    body = real_client.get(f"/songs?sort_by={field}&order={order}&size=100").json()
    got = body["songs"]
    assert body["total"] == len(got) == 25
    assert {s["id"] for s in got} == {s["id"] for s in on_disk}  # nothing lost or duplicated

    def comparable(song):
        value = song[field]
        return value.casefold() if field == "title" else value

    present = [s for s in got if s[field] is not None]
    missing = [s for s in got if s[field] is None]
    assert got == present + missing  # nulls last
    assert len(missing) == sum(1 for s in on_disk if s.get(field) is None)
    values = [comparable(s) for s in present]
    assert values == sorted(values, reverse=(order == "desc"))
    # equal values are ordered by id ascending
    for a, b in zip(present, present[1:]):
        if comparable(a) == comparable(b):
            assert a["id"] < b["id"]


def test_real_dataset_sorted_by_duration_across_pages(real_client):
    on_disk = json.loads(DATA_FILE.read_text())
    expected = [s["id"] for s in sorted(on_disk, key=lambda s: (s["duration_ms"], s["id"]))]
    got = []
    for page in (1, 2, 3):
        got += ids(real_client.get(f"/songs?sort_by=duration_ms&page={page}").json())
    assert got == expected
    # The shortest song is Yesterday (125,666 ms); the corrected Sunflower is 158,000 ms.
    first = real_client.get("/songs?sort_by=duration_ms&size=1").json()["songs"][0]
    assert (first["title"], first["duration_ms"]) == ("Yesterday", 125_666)
