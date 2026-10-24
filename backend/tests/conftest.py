import pytest
from fastapi.testclient import TestClient

import app.main
from app.main import create_app


@pytest.fixture(scope="session", autouse=True)
def isolated_default_ratings_db(tmp_path_factory):
    """No test may touch the real ratings database: any app built without an
    explicit ratings_path gets a throwaway file instead.  Session-scoped so it is
    in place before module-scoped fixtures build their apps."""
    real = app.main.RATINGS_DB
    snapshot = (real.stat().st_mtime_ns, real.read_bytes()) if real.exists() else None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(app.main, "RATINGS_DB", tmp_path_factory.mktemp("default-ratings") / "ratings.db")
        yield
    after = (real.stat().st_mtime_ns, real.read_bytes()) if real.exists() else None
    assert after == snapshot, f"the test suite modified the real ratings database {real}"


@pytest.fixture(scope="module")
def real_client(tmp_path_factory):
    """The real normalized dataset, with ratings in a throwaway database."""
    ratings = tmp_path_factory.mktemp("real-ratings") / "ratings.db"
    with TestClient(create_app(ratings_path=ratings)) as c:
        yield c
