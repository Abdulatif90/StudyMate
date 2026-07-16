"""Inngest client — the app's connection to Inngest for async jobs.

One client, built once and shared by both the ASGI handler (`app/main.py`, which
serves registered functions at `/api/inngest`) and the event-send path
(`documents.service.enqueue_document_processing`).

The client itself constructs fine without keys so the app/tests can boot before an
Inngest account exists (`is_production=False` runs against the local Dev Server).
Actually *sending* an event without an `INNGEST_EVENT_KEY`, though, is a deployment
mistake — `require_event_key()` raises a bare `RuntimeError` at that point of use,
same pattern as `db.py`/`embedding.py`/`llm.py`, rather than silently dropping the
event and leaving documents stuck on `pending`.
"""

from __future__ import annotations

from functools import lru_cache

import inngest

from app.core.config import get_settings

APP_ID = "studymate"


@lru_cache
def get_inngest_client() -> inngest.Inngest:
    settings = get_settings()
    return inngest.Inngest(
        app_id=APP_ID,
        event_key=settings.inngest_event_key,
        signing_key=settings.inngest_signing_key,
        is_production=settings.is_production,
    )


def require_event_key() -> None:
    """Raise if no `INNGEST_EVENT_KEY` is configured — call before sending an event
    in a context where a missing key means events would silently vanish."""
    if not get_settings().inngest_event_key:
        raise RuntimeError(
            "INNGEST_EVENT_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
