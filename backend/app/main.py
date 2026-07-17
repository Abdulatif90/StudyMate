"""StudyMate API — FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

import inngest.fast_api
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.inngest_client import get_inngest_client
from app.modules.ask.router import conversations_router
from app.modules.ask.router import router as ask_router
from app.modules.billing.router import router as billing_router
from app.modules.billing.service import PlanLimitExceededError
from app.modules.documents.jobs import process_document_fn
from app.modules.documents.router import router as documents_router
from app.modules.flashcards.router import flashcards_router
from app.modules.flashcards.router import router as flashcards_subject_router
from app.modules.progress.router import overall_router as progress_overall_router
from app.modules.progress.router import router as progress_router
from app.modules.quiz.router import router as quiz_router
from app.modules.subjects.router import router as subjects_router

settings = get_settings()

app = FastAPI(
    title="StudyMate API",
    version="0.1.0",
    description="AI study assistant — RAG over your own materials.",
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
