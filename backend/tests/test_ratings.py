"""Persistent ratings: PUT/GET /songs/{id}/rating and the `rating` field of GET /songs."""

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import SONG_FIELDS, client_for, client_with, ids, make_song, write_songs

from app.main import create_app
from app.ratings import RatingsStore

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path):
    with client_for(tmp_path, 25) as c:
        yield c


def rate(client, song_id, rating):
    return client.put(f"/songs/{song_id}/rating", json={"rating": rating})


def rating_of(client, song_id):
    response = client.get(f"/songs/{song_id}/rating")
    assert response.status_code == 200
    return response.json()["rating"]


def all_ratings(client) -> dict:
    songs = client.get("/songs", params={"size": 100}).json()["songs"]
    return {s["id"]: s["rating"] for s in songs}


# --- creating and updating ------------------------------------------------------------


def test_rating_a_song_returns_the_song_id_and_rating(client):
    response = rate(client, "id003", 4)
    assert response.status_code == 200
    assert response.json() == {"song_id": "id003", "rating": 4}


def test_rating_can_be_read_back_and_unrated_songs_are_null(client):
    assert rating_of(client, "id003") is None
    assert client.get("/songs/id003/rating").json() == {"song_id": "id003", "rating": None}
    rate(client, "id003", 4)
    assert client.get("/songs/id003/rating").json() == {"song_id": "id003", "rating": 4}


def test_rating_appears_on_the_song_in_the_list(client):
    assert all(s["rating"] is None for s in client.get("/songs").json()["songs"])
    rate(client, "id003", 2)
    songs = {s["id"]: s for s in client.get("/songs").json()["songs"]}
    assert songs["id003"]["rating"] == 2
    assert songs["id004"]["rating"] is None
    assert all(set(s) == SONG_FIELDS for s in songs.values())


def test_rating_can_be_updated_and_the_last_value_wins(client):
    rate(client, "id003", 2)
    assert rate(client, "id003", 5).json()["rating"] == 5
    assert rating_of(client, "id003") == 5
    rate(client, "id003", 1)
    assert rating_of(client, "id003") == 1
    assert sum(r is not None for r in all_ratings(client).values()) == 1  # still one rating, not three


def test_rating_the_same_value_twice_is_fine(client):
    assert rate(client, "id003", 3).status_code == rate(client, "id003", 3).status_code == 200
    assert rating_of(client, "id003") == 3


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_every_value_from_1_to_5_is_accepted(client, value):
    assert rate(client, "id000", value).status_code == 200
    assert rating_of(client, "id000") == value


# --- several songs --------------------------------------------------------------------


def test_ratings_of_several_songs_are_independent(client):
    wanted = {"id000": 5, "id007": 1, "id012": 3, "id024": 4}
    for song_id, value in wanted.items():
        rate(client, song_id, value)
    ratings = all_ratings(client)
    assert {k: v for k, v in ratings.items() if v is not None} == wanted
    assert len(ratings) == 25


def test_updating_one_song_does_not_change_the_others(client):
    for song_id, value in {"id001": 2, "id002": 3, "id003": 4}.items():
        rate(client, song_id, value)
    rate(client, "id002", 5)
    assert [rating_of(client, f"id00{n}") for n in (1, 2, 3)] == [2, 5, 4]


# --- invalid ratings -------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, 6, 100, 3.5, 4.0, "4", "four", "", None, True, False, [4], {"a": 1}])
def test_invalid_rating_values_are_rejected_with_422_and_nothing_is_stored(client, value):
    response = rate(client, "id003", value)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "rating"]
    assert rating_of(client, "id003") is None


def test_an_invalid_update_keeps_the_previous_rating(client):
    rate(client, "id003", 4)
    assert rate(client, "id003", 9).status_code == 422
    assert rating_of(client, "id003") == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {}},
        {"json": {"rate": 3}},
        {"json": {"rating": 3, "extra": 1}},
        {"json": [3]},
        {"json": 3},
        {"json": None},
        {"content": "not json", "headers": {"content-type": "application/json"}},
        {"content": '{"rating": 3}'},  # no JSON content type
        {},
    ],
)
def test_malformed_or_missing_bodies_are_rejected_with_422(client, kwargs):
    assert client.put("/songs/id003/rating", **kwargs).status_code == 422
    assert rating_of(client, "id003") is None


def test_rating_in_the_query_string_is_not_accepted(client):
    assert client.put("/songs/id003/rating?rating=4").status_code == 422
    assert rating_of(client, "id003") is None


# --- unknown songs ----------------------------------------------------------------------


@pytest.mark.parametrize("song_id", ["nope", "ID000", "id000 ", "id0000", "Song 3", "x" * 500])
def test_unknown_song_id_is_404_for_get_and_put_and_stores_nothing(client, song_id):
    put = rate(client, song_id, 3)
    assert put.status_code == 404
    assert song_id in put.json()["detail"]
    assert client.get(f"/songs/{song_id}/rating").status_code == 404
    assert set(all_ratings(client).values()) == {None}


def test_unknown_song_is_404_even_when_the_body_is_invalid(client):
    # The song is looked up first, so the caller learns the id is wrong.
    assert rate(client, "nope", 99).status_code == 404


def test_songs_are_rated_by_id_not_by_title(tmp_path):
    songs = [make_song(0), make_song(1)]
    songs[0]["title"] = songs[1]["title"] = "Perfect"  # same title, different songs
    with client_with(tmp_path, songs) as c:
        assert rate(c, "id001", 5).status_code == 200
        assert rating_of(c, "id000") is None and rating_of(c, "id001") == 5
        assert c.put("/songs/Perfect/rating", json={"rating": 5}).status_code == 404


def test_unsupported_methods_on_the_rating_route(client):
    assert client.post("/songs/id003/rating", json={"rating": 3}).status_code == 405
    assert client.delete("/songs/id003/rating").status_code == 405


# --- persistence -------------------------------------------------------------------------


def test_ratings_survive_an_application_restart(tmp_path):
    ratings_db = tmp_path / "state" / "ratings.db"
    songs = [make_song(n) for n in range(5)]
    with client_with(tmp_path, songs, ratings_db) as first:
        rate(first, "id001", 5)
        rate(first, "id003", 2)
        rate(first, "id003", 3)  # an update, also persisted
    with client_with(tmp_path, songs, ratings_db) as second:  # a brand-new app instance
        assert rating_of(second, "id001") == 5
        assert rating_of(second, "id003") == 3
        assert rating_of(second, "id000") is None
        assert [s["rating"] for s in second.get("/songs").json()["songs"]] == [None, 5, None, 3, None]
        rate(second, "id000", 1)  # new writes keep the old ones
    with client_with(tmp_path, songs, ratings_db) as third:
        assert [s["rating"] for s in third.get("/songs").json()["songs"]] == [1, 5, None, 3, None]


def test_a_rating_written_by_another_process_is_visible_to_the_api(tmp_path):
    ratings_db = tmp_path / "ratings.db"
    code = "import sys; from pathlib import Path; from app.ratings import RatingsStore; RatingsStore(Path(sys.argv[1])).set('id002', 4)"
    subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, '.'); {code}", str(ratings_db)], cwd=BACKEND, check=True)
    with client_with(tmp_path, [make_song(n) for n in range(5)], ratings_db) as c:
        assert rating_of(c, "id002") == 4


def test_separate_stores_on_one_file_see_each_other(tmp_path):
    a, b = RatingsStore(tmp_path / "r.db"), RatingsStore(tmp_path / "r.db")
    a.set("x", 1)
    b.set("y", 2)
    assert a.all() == b.all() == {"x": 1, "y": 2}
    assert (a.get("x"), b.get("y"), a.get("missing")) == (1, 2, None)


def test_the_ratings_store_creates_its_directory(tmp_path):
    store = RatingsStore(tmp_path / "a" / "b" / "ratings.db")
    store.set("x", 3)
    assert (tmp_path / "a" / "b" / "ratings.db").exists()


# --- keeping ratings separate from the song data -------------------------------------------


def test_rating_never_modifies_the_songs_file_or_the_stored_songs(tmp_path):
    songs_path = write_songs(tmp_path, [make_song(n) for n in range(5)])
    before = songs_path.read_bytes()
    ratings_db = tmp_path / "ratings.db"
    with TestClient(create_app(songs_path, ratings_db)) as c:
        rate(c, "id001", 5)
        rate(c, "id001", 2)
        assert c.get("/songs").json()["songs"][1]["rating"] == 2
        assert all("rating" not in s for s in c.app.state.songs)  # in-memory dataset untouched
    assert songs_path.read_bytes() == before
    assert ratings_db.exists() and ratings_db != songs_path


def test_ratings_for_songs_not_in_the_dataset_are_ignored(tmp_path):
    ratings_db = tmp_path / "ratings.db"
    RatingsStore(ratings_db).set("ghost", 5)  # e.g. left over from an older dataset
    with client_with(tmp_path, [make_song(n) for n in range(3)], ratings_db) as c:
        body = c.get("/songs").json()
        assert body["total"] == 3 and "ghost" not in ids(body)
        assert c.get("/songs/ghost/rating").status_code == 404


# --- rating as a sort key ----------------------------------------------------------------------


def test_sort_by_rating_puts_unrated_songs_last_in_both_directions(client):
    for song_id, value in {"id005": 3, "id002": 5, "id009": 3, "id001": 1}.items():
        rate(client, song_id, value)

    def order(direction):
        body = client.get("/songs", params={"sort_by": "rating", "order": direction, "size": 100}).json()
        return [(s["id"], s["rating"]) for s in body["songs"]]

    rated_asc = [("id001", 1), ("id005", 3), ("id009", 3), ("id002", 5)]  # tie 3/3 broken by id ascending
    rated_desc = [("id002", 5), ("id005", 3), ("id009", 3), ("id001", 1)]
    unrated = [(f"id{n:03d}", None) for n in range(25) if f"id{n:03d}" not in {"id005", "id002", "id009", "id001"}]
    assert order("asc") == rated_asc + unrated
    assert order("desc") == rated_desc + unrated


def test_sort_by_rating_is_global_across_pages(client):
    rate(client, "id024", 5)  # the last song in the file is the best rated
    first = client.get("/songs", params={"sort_by": "rating", "order": "desc", "size": 1}).json()
    assert ids(first) == ["id024"] and first["total"] == 25


def test_rating_filter_search_sort_paginate_together(tmp_path):
    songs = [make_song(n) for n in range(12)]
    for song in songs:
        song["title"] = "Same" if song["id"] in {"id001", "id004", "id006", "id009", "id010"} else "Other"
    with client_with(tmp_path, songs) as c:
        for song_id, value in {"id001": 2, "id004": 5, "id006": 4, "id010": 5, "id003": 5}.items():
            rate(c, song_id, value)  # id003 is rated 5 but is not titled "Same"
        body = c.get("/songs", params={"title": "same", "sort_by": "rating", "order": "desc", "size": 2}).json()
        assert ids(body) == ["id004", "id010"]  # the two 5s, tie broken by id; id003 is filtered out
        assert (body["total"], body["total_pages"]) == (5, 3)
        page3 = c.get("/songs", params={"title": "same", "sort_by": "rating", "order": "desc", "size": 2, "page": 3}).json()
        assert ids(page3) == ["id009"] and page3["songs"][0]["rating"] is None  # unrated last


# --- concurrency -----------------------------------------------------------------------------------


def test_concurrent_writers_to_different_songs_lose_nothing(tmp_path):
    store = RatingsStore(tmp_path / "ratings.db")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda n: store.set(f"song{n:03d}", n % 5 + 1), range(200)))
    assert store.all() == {f"song{n:03d}": n % 5 + 1 for n in range(200)}


def test_concurrent_updates_to_one_song_end_with_a_valid_single_row(tmp_path):
    store = RatingsStore(tmp_path / "ratings.db")
    store.set("other", 4)
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda n: store.set("hot", n % 5 + 1), range(200)))
    ratings = store.all()
    assert set(ratings) == {"hot", "other"} and ratings["other"] == 4
    assert ratings["hot"] in {1, 2, 3, 4, 5}


def test_concurrent_requests_through_the_api(tmp_path):
    songs = [make_song(n) for n in range(40)]
    with client_with(tmp_path, songs) as c:
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda n: rate(c, f"id{n:03d}", n % 5 + 1).status_code, range(40)))
        assert set(statuses) == {200}
        assert all_ratings(c) == {f"id{n:03d}": n % 5 + 1 for n in range(40)}


def test_separate_processes_writing_at_once_lose_nothing(tmp_path):
    ratings_db = tmp_path / "ratings.db"
    RatingsStore(ratings_db)
    code = (
        "import sys; sys.path.insert(0, '.'); from pathlib import Path; from app.ratings import RatingsStore; "
        "s = RatingsStore(Path(sys.argv[1])); w = sys.argv[2]; "
        "[s.set(f'w{w}-{n}', n % 5 + 1) for n in range(40)]"
    )
    procs = [subprocess.Popen([sys.executable, "-I", "-c", code, str(ratings_db), str(w)], cwd=BACKEND) for w in range(4)]
    assert [p.wait() for p in procs] == [0, 0, 0, 0]
    ratings = RatingsStore(ratings_db).all()
    assert len(ratings) == 160
    assert ratings == {f"w{w}-{n}": n % 5 + 1 for w in range(4) for n in range(40)}


# --- store robustness ------------------------------------------------------------------------------


def test_the_database_itself_rejects_out_of_range_values(tmp_path):
    store = RatingsStore(tmp_path / "ratings.db")
    for bad in (0, 6, -1):
        with pytest.raises(sqlite3.IntegrityError):
            store.set("x", bad)
    assert store.all() == {}


def test_a_corrupt_ratings_file_stops_startup_with_a_clear_error(tmp_path):
    bad = tmp_path / "ratings.db"
    bad.write_bytes(b"this is not a sqlite database" * 20)
    with pytest.raises(RuntimeError, match="Cannot open ratings database") as error:
        with client_with(tmp_path, [make_song(0)], bad):
            pass
    assert str(bad) in str(error.value)
    assert bad.read_bytes().startswith(b"this is not")  # left untouched, not overwritten


def test_an_unusable_ratings_path_stops_startup_with_a_clear_error(tmp_path):
    with pytest.raises(RuntimeError, match="Cannot open ratings database"):
        with client_with(tmp_path, [make_song(0)], tmp_path):  # a directory, not a file
            pass
