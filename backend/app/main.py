"""StudyMate API — FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.auth import get_current_user_id, get_org_context
from app.core.config import get_settings
from app.core.inngest_client import get_inngest_client
from app.core.org import OrgContext, org_capability
from app.core.sentry import init_sentry
from app.modules.ask.router import conversations_router
from app.modules.ask.router import router as ask_router
from app.modules.assignments.router import router as assignments_router
from app.modules.billing.router import router as billing_router
from app.modules.billing.service import PlanLimitExceededError
from app.modules.documents.jobs import process_document_fn
from app.modules.documents.router import router as documents_router
from app.modules.flashcards.router import flashcards_router
from app.modules.flashcards.router import router as flashcards_subject_router
from app.modules.progress.router import overall_router as progress_overall_router
from app.modules.progress.router import router as progress_router
from app.modules.quiz.router import router as quiz_router
from app.modules.referral.router import router as referral_router
from app.modules.subjects.router import router as subjects_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Runs once, at real server startup — deliberately NOT at module import time.

    `sentry_sdk.init()` globally patches process-wide machinery (the exception
    middleware class, `sys.excepthook`, ...), so it must run exactly once per real
    process. Module-level init would ALSO fire on every `pytest` run that imports this
    module (every test file that builds a `TestClient` does), which — the moment a real
    `SENTRY_DSN` lands in `.env` for actual use — would start shipping test-generated
    exceptions to a real Sentry project on every offline test run. A lifespan hook only
    runs when something actually drives the ASGI lifespan protocol: real `uvicorn`
    serving does; this repo's `TestClient(app)` usage (no test uses the `with
    TestClient(app) as client:` form) does not. No-op unless SENTRY_DSN is set (see
    init_sentry's docstring). PlanLimitExceededError is excluded — it's an expected 402
    (handled by the app-wide handler below), not an error worth alerting on.
    """
    init_sentry(ignored_exceptions=[PlanLimitExceededError])
    yield


app = FastAPI(
    title="StudyMate API",
    version="0.1.0",
    description="AI study assistant — RAG over your own materials.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(subjects_router)
app.include_router(documents_router)
app.include_router(ask_router)
app.include_router(conversations_router)
app.include_router(quiz_router)
app.include_router(flashcards_subject_router)
app.include_router(flashcards_router)
app.include_router(progress_router)
app.include_router(progress_overall_router)
app.include_router(billing_router)
app.include_router(referral_router)
app.include_router(assignments_router)


@app.exception_handler(PlanLimitExceededError)
async def plan_limit_exceeded_handler(
    _request: Request, exc: PlanLimitExceededError
) -> JSONResponse:
    """Plan-quota rejections -> 402 Payment Required, application-wide.

    Registered once here rather than as an identical `except` block in each of the four
    guarded routers (subjects/documents/quiz/flashcards): the mapping is the same
    everywhere, so one handler keeps those routers thin and gives any future guarded
    path the same behavior for free. Per-router try/except remains the pattern for
    *module-specific* exceptions (SubjectNotFoundError, QuizGenerationError, ...), which
    genuinely differ per route.

    The body names the limit and its cap (see PlanLimitExceededError.message) so the
    client can say "you've hit 3 of 3 subjects" rather than a generic "quota exceeded",
    and carries them as fields so a frontend can act on them without parsing prose.
    """
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={
            "detail": exc.message,
            "limit": exc.limit.value,
            "plan": exc.plan.value,
            "cap": exc.cap,
        },
    )


# Serve the Inngest functions at /api/inngest (Inngest calls back here to run jobs).
inngest.fast_api.serve(app, get_inngest_client(), [process_document_fn])


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check — confirms the API process is up."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/org")
def whoami_org(
    user_id: str = Depends(get_current_user_id),
    org_ctx: OrgContext = Depends(get_org_context),
) -> dict[str, str | None]:
    """The caller's active-organization context as the backend actually sees it, read
    from the verified Clerk session JWT (`get_org_context`).

    Permanent, authenticated debug/verification endpoint (Phase 5 increment 2, Step 0):
    org-scoped content sharing is built entirely on `org_id`/`org_role` arriving in the
    real token. Increment 1 only exercised `get_org_context` in unit tests, never
    against a live token — this endpoint lets the org sharing model be confirmed
    end-to-end: signed in with an active org, `org_id`/`org_role` must be non-null here.
    If they are null in a real session that HAS an active org, Clerk's session-token JWT
    template is missing the org claims and must be configured (backend code is correct;
    do NOT touch `.env`/Clerk config from here). Returns only the caller's own ids —
    never anyone else's — so it's safe to keep enabled.
    """
    return {
        "user_id": user_id,
        "org_id": org_ctx.org_id,
        "org_role": org_ctx.org_role,
        "capability": org_capability(org_ctx.org_role),
    }
