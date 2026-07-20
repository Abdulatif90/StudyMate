"""Vercel Python-runtime entrypoint.

Vercel's Python runtime looks for a FastAPI instance named `app` at a supported
entrypoint (`api/index.py` is one of them; `pyproject.toml`'s `[tool.vercel]
entrypoint = "api.index:app"` pins it explicitly to avoid any multi-entrypoint
ambiguity). This module does nothing but **re-export** the existing application —
it never redefines it — so local `uvicorn app.main:app --reload` is completely
unaffected and there is exactly one source of truth for the app.

The whole FastAPI app becomes a single Vercel Function (Fluid compute). SSE
streaming (`/subjects/{id}/ask/stream`) is supported on the Python runtime; see
`docs/DEPLOYMENT.md` for the required `VERCEL_FORCE_PYTHON_STREAMING=1` env var and
the `maxDuration` set in `vercel.json`.
"""

from __future__ import annotations

from app.main import app

__all__ = ["app"]
