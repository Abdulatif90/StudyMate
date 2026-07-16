"""Inngest function for async document processing. Thin — mirrors the router: it
pulls ids off the event, opens a DB session, and hands off to
`service.process_document` (which owns all the parse/chunk/embed/persist logic and
the idempotency/failed-status guarantees). Registered on the shared client and
served at `/api/inngest` (see `app/main.py`).
"""

from __future__ import annotations

import uuid

import inngest
from sqlmodel import Session

from app.core.db import get_engine
from app.core.inngest_client import get_inngest_client
from app.modules.documents import service


@get_inngest_client().create_function(
    fn_id="process-document",
    trigger=inngest.TriggerEvent(event=service.DOCUMENT_UPLOADED_EVENT),
    # Beyond Inngest's default retries: parse/embed can fail transiently (Cohere rate
    # limits, network). process_document is idempotent, so retrying is safe.
    retries=3,
)
def process_document_fn(ctx: inngest.ContextSync) -> dict[str, str]:
    document_id = ctx.event.data["document_id"]
    owner_id = ctx.event.data["owner_id"]

    # Wrapped in a step so a retry after this succeeded resumes past it (Inngest
    # memoizes the step's result) rather than re-parsing/re-embedding needlessly.
    def _run() -> str:
        with Session(get_engine()) as session:
            document = service.process_document(session, owner_id, uuid.UUID(document_id))
            if document is None:
                return "missing"
            return document.status.value

    result = ctx.step.run("process-document", _run)
    return {"document_id": document_id, "status": result}
