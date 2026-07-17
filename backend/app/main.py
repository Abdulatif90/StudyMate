"""StudyMate API — FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

import inngest.fast_api
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.inngest_client import get_inngest_client
from app.modules.ask.router import conversations_router
from app.modules.ask.router import router as ask_router
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

# Serve the Inngest functions at /api/inngest (Inngest calls back here to run jobs).
inngest.fast_api.serve(app, get_inngest_client(), [process_document_fn])


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check — confirms the API process is up."""
    return {"status": "ok", "environment": settings.environment}
