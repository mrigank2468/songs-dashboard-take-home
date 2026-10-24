"""Startup validation, CORS, the public API contract, and cross-feature behaviour."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from helpers import SONG_FIELDS, client_with, ids, make_song, write_songs

from app.data import DATA_FILE, load_songs
from app.main import CORS_ORIGINS, create_app

DATA_DIR = DATA_FILE.parent
PROTECTED = ["songs_part1.json", "songs_part2.json", "songs_normalized.json", "data_quality_report.json"]


def digest(name: str) -> str:
    return hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()


# --- startup validation -----------------------------------------------------------------


def startup_error(tmp_path, content: str | None, exc):
    path = tmp_path / "songs.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(exc) as error:
        with TestClient(create_app(path, tmp_path / "ratings.db")):
            pass
    assert str(path) in str(error.value)  # every failure names the file
    return str(error.value)


def test_missing_data_file_fails_startup_naming_the_file(tmp_path):
    startup_error(tmp_path, None, FileNotFoundError)


def test_invalid_json_fails_startup_naming_the_file(tmp_path):
    assert "not valid JSON" in startup_error(tmp_path, '[{"id": ', ValueError)


@pytest.mark.parametrize("content", ['{"songs": []}', '"text"', "3", "null"])
def test_a_top_level_value_that_is_not_an_array_fails_startup(tmp_path, content):
    assert "JSON array" in startup_error(tmp_path, content, ValueError)


def test_an_item_that_is_not_an_object_fails_startup(tmp_path):
    assert "item 1 is not a song object" in startup_error(tmp_path, json.dumps([make_song(0), 5]), ValueError)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda s: s.pop("id"), "id"),
        (lambda s: s.pop("title"), "title"),
        (lambda s: s.update(energy="loud"), "energy"),
        (lambda s: s.update(mood=1.5), "mood"),
        (lambda s: s.update(id=7), "id"),
        (lambda s: s.update(sources="part1") or s.pop("tempo"), "tempo"),
    ],
)
def test_a_record_that_is_not_a_valid_song_fails_startup_naming_the_item(tmp_path, mutate, expected):
    bad = make_song(1)
    mutate(bad)
    message = startup_error(tmp_path, json.dumps([make_song(0), bad]), ValueError)
    assert "item 1 is not a valid song" in message and expected in message


def test_a_repeated_id_fails_startup(tmp_path):
    message = startup_error(tmp_path, json.dumps([make_song(0), make_song(1), make_song(0)]), ValueError)
    assert "item 2 repeats id 'id000'" in message


def test_nulls_and_extra_keys_are_valid_in_the_data_file(tmp_path):
    song = make_song(0)
    song.update(title=None, energy=None, tempo=None, duration_ms=None, extra="ignored")
    with client_with(tmp_path, [song]) as c:
        served = c.get("/songs").json()["songs"][0]
    assert served["title"] is None and served["tempo"] is None and "extra" not in served


def test_an_empty_array_is_a_valid_dataset(tmp_path):
    assert load_songs(write_songs(tmp_path, [])) == []


def test_load_songs_never_writes_the_file(tmp_path):
    path = write_songs(tmp_path, [make_song(0)])
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    load_songs(path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (before, mtime)


# --- source and normalized data are never modified --------------------------------------------


def test_using_the_whole_api_leaves_every_data_file_unchanged(tmp_path):
    before = {name: digest(name) for name in PROTECTED}
    listing = sorted(p.name for p in DATA_DIR.iterdir())
    with TestClient(create_app(ratings_path=tmp_path / "ratings.db")) as c:
        c.get("/songs")
        c.get("/songs", params={"sort_by": "tempo", "order": "desc", "title": "perfect", "page": 2})
        song_id = c.get("/songs").json()["songs"][0]["id"]
        assert c.put(f"/songs/{song_id}/rating", json={"rating": 5}).status_code == 200
        c.put(f"/songs/{song_id}/rating", json={"rating": 9})
        c.put("/songs/nope/rating", json={"rating": 3})
    assert {name: digest(name) for name in PROTECTED} == before
    assert sorted(p.name for p in DATA_DIR.iterdir()) == listing  # no stray files, e.g. a ratings.db, in data/


def test_the_normalized_file_still_has_sources_and_the_api_still_hides_them(real_client):
    on_disk = json.loads(DATA_FILE.read_text())
    assert all(song["sources"] for song in on_disk)
    songs = real_client.get("/songs", params={"size": 100}).json()["songs"]
    assert len(songs) == len(on_disk) == 25
    assert all("sources" not in s and set(s) == SONG_FIELDS for s in songs)


# --- public contract ------------------------------------------------------------------------------


def test_openapi_documents_the_public_song_and_sort_fields(real_client):
    schema = real_client.get("/openapi.json").json()
    props = set(schema["components"]["schemas"]["Song"]["properties"])
    assert props == SONG_FIELDS and "sources" not in props
    sort_by = next(p for p in schema["paths"]["/songs"]["get"]["parameters"] if p["name"] == "sort_by")
    values = set(schema["components"]["schemas"]["SortField"]["enum"])
    assert values == SONG_FIELDS and "sort_by" == sort_by["name"]
    assert {p["name"] for p in schema["paths"]["/songs"]["get"]["parameters"]} == {"page", "size", "sort_by", "order", "title"}
    assert set(schema["paths"]["/songs/{song_id}/rating"]) == {"get", "put"}


def test_the_documented_response_shape(real_client):
    body = real_client.get("/songs").json()
    assert list(body) == ["songs", "page", "size", "total", "total_pages"]
    assert isinstance(body["songs"], list) and all(isinstance(body[k], int) for k in list(body)[1:])


# --- CORS -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("origin", CORS_ORIGINS)
def test_cors_allows_the_local_dev_frontend(real_client, origin):
    get = real_client.get("/songs", headers={"Origin": origin})
    assert get.headers["access-control-allow-origin"] == origin
    preflight = real_client.options(
        "/songs/x/rating",
        headers={"Origin": origin, "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "PUT" in preflight.headers["access-control-allow-methods"]


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:3000", "http://localhost:5173.evil.example", "null"])
def test_cors_does_not_allow_other_origins(real_client, origin):
    get = real_client.get("/songs", headers={"Origin": origin})
    assert get.status_code == 200 and "access-control-allow-origin" not in get.headers
    preflight = real_client.options("/songs", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert preflight.status_code == 400 and "access-control-allow-origin" not in preflight.headers


def test_cors_is_not_a_wildcard_and_only_allows_the_methods_the_api_uses(real_client):
    assert "*" not in CORS_ORIGINS
    response = real_client.get("/songs", headers={"Origin": "http://elsewhere.example"})
    assert response.headers.get("access-control-allow-origin") != "*"
    preflight = real_client.options(
        "/songs", headers={"Origin": CORS_ORIGINS[0], "Access-Control-Request-Method": "DELETE"}
    )
    assert preflight.status_code == 400


def test_cors_origins_are_configurable(tmp_path):
    with client_with(tmp_path, [make_song(0)], cors_origins=("http://app.example",)) as c:
        assert c.get("/songs", headers={"Origin": "http://app.example"}).headers["access-control-allow-origin"] == "http://app.example"
        assert "access-control-allow-origin" not in c.get("/songs", headers={"Origin": CORS_ORIGINS[0]}).headers


# --- the features together --------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_every_sort_field_with_search_keeps_nulls_last_ties_by_id_and_metadata(real_client, order):
    on_disk = {s["id"]: s for s in json.loads(DATA_FILE.read_text())}
    for field in sorted(SONG_FIELDS - {"rating"}):
        body = real_client.get("/songs", params={"title": "", "sort_by": field, "order": order, "size": 7, "page": 2}).json()
        full = real_client.get("/songs", params={"sort_by": field, "order": order, "size": 100}).json()["songs"]
        assert (body["page"], body["size"], body["total"], body["total_pages"]) == (2, 7, 25, 4), field
        assert ids(body) == [s["id"] for s in full[7:14]], field  # a page is a slice of the whole sorted set
        values = [on_disk[s["id"]][field] for s in full]
        nulls = [v is None for v in values]
        assert nulls == sorted(nulls), (field, order)  # every null after every value


def test_empty_dataset_everywhere(tmp_path):
    with client_with(tmp_path, []) as c:
        empty = {"songs": [], "page": 1, "size": 10, "total": 0, "total_pages": 0}
        assert c.get("/songs").json() == empty
        assert c.get("/songs", params={"title": "x", "sort_by": "tempo", "order": "desc"}).json() == empty
        assert c.get("/songs/anything/rating").status_code == 404
        assert c.put("/songs/anything/rating", json={"rating": 3}).status_code == 404


def test_validation_errors_are_json_with_locations(real_client):
    for url, loc in [("/songs?page=0", "page"), ("/songs?size=101", "size"), ("/songs?sort_by=x", "sort_by"), ("/songs?order=x", "order")]:
        response = real_client.get(url)
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        assert response.json()["detail"][0]["loc"] == ["query", loc]


def test_the_title_parameter_accepts_any_text_without_error(real_client):
    for text in ["%", "_", "'; DROP TABLE ratings; --", "\u0000", "🎵", "a" * 2000, "<script>", "%00"]:
        response = real_client.get("/songs", params={"title": text})
        assert response.status_code == 200 and response.json()["total"] == 0, text
