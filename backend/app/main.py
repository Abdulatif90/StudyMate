"""StudyMate API — FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.ask.router import router as ask_router
from app.modules.documents.router import router as documents_router
from app.modules.subjects.router import router as subjects_router

settings = get_settings()

app = FastAPI(
    title="StudyMate API",
    version="0.1.0",
    description="AI study assistant — RAG over your own materials.",
)

app.include_router(subjects_router)
app.include_router(documents_router)
app.include_router(ask_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check — confirms the API process is up."""
    return {"status": "ok", "environment": settings.environment}
