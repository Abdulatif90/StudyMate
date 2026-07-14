"""Tests for app.core.db — engine creation, without touching a real database.

`create_engine` is lazy (SQLAlchemy doesn't open a connection until first
use), so these stay unit tests: no live Postgres needed.
"""

from types import SimpleNamespace

import pytest

from app.core import db


@pytest.fixture(autouse=True)
def _clear_engine_cache():
    db.get_engine.cache_clear()
    yield
    db.get_engine.cache_clear()


def test_get_engine_raises_without_database_url(monkeypatch):
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_url=None))
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db.get_engine()


def test_get_engine_builds_engine_from_url(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://user:pass@localhost/testdb"),
    )
    engine = db.get_engine()
    assert engine.url.host == "localhost"
    assert engine.url.database == "testdb"
