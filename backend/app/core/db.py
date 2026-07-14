"""Database engine and session — SQLModel (a thin, typed layer over SQLAlchemy).

One `Engine` per process holds the connection pool to Neon; each request
gets its own short-lived `Session` from `get_session`, which callers use as
a FastAPI dependency so the session is always closed after the request.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlmodel import Session, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine():
    """Build (once) the SQLAlchemy engine for the configured Postgres URL.

    `pool_pre_ping` checks a pooled connection is still alive before handing
    it out — Neon can drop idle connections, and this avoids surfacing that
    as a random query failure.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to backend/.env — see backend/.env.example."
        )
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, closed when the request ends.

    Usage: `session: Session = Depends(get_session)` in a route/service.
    """
    with Session(get_engine()) as session:
        yield session
