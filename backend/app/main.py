"""StudyMate API — FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="StudyMate API",
    version="0.1.0",
    description="AI study assistant — RAG over your own materials.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check — confirms the API process is up."""
    return {"status": "ok", "environment": settings.environment}
