# CLAUDE.md — StudyMate

Router for anyone (human or AI) working on this repo. **Read this first, then `docs/PROGRESS.md`.**

## What this is
Education RAG SaaS. Students upload materials → cited Q&A, auto-summary, quizzes,
flashcards (SM-2), progress. Multilingual, global students.

## Stack (don't change without an ADR in `docs/DECISIONS.md`)
- **Backend:** Python 3.12 + FastAPI + SQLModel + Alembic; Neon Postgres + pgvector;
  Clerk (auth via JWKS); Inngest (jobs); Cohere (embeddings); Claude/Anthropic (generation);
  R2 (files); Polar (billing).
- **Frontend:** Next.js 15 App Router + React 19 + TS; Tailwind + shadcn/ui; TanStack Query;
  next-intl. Typed API client from FastAPI OpenAPI — **no tRPC** (backend is Python).

## Structure
- `backend/app/core` — config, db, auth
- `backend/app/modules/<domain>` — `router` + `service` + `schemas` + `models` per domain
  (subjects, documents, ask, quiz, flashcards, progress, billing)
- `backend/app/shared` — shared utilities
- `backend/tests` — pytest
- `frontend/` — Next.js (added later)

## Rules
1. Business logic in **services**, not routes. Keep routers thin.
2. Every DB query filtered by the current user (**tenant scoping / ownership**).
3. **Never swallow errors** — handle explicitly, return clear codes.
4. Every change ships with a **test** (pytest/Vitest) that passes.
5. **Secrets in env only** — never in code, logs, or responses.
6. DRY · SOLID (single responsibility) · KISS · YAGNI. Small, focused functions.
7. **Frontend must be responsive (mobile-first) and use semantic color tokens** —
   follow `docs/FRONTEND.md` for every page/component.

## Git
- Branches: `main` (prod) ← `develop` (integration) ← `feature/*`.
- Atomic commits, **Conventional Commits** (`feat:`/`fix:`/`refactor:`/`test:`/`docs:`/`chore:`).
- Never commit directly to `main` — merge from `develop`.
- **Push after every increment** — `git push` to `origin` (GitHub) so the remote stays in sync.

## Commands (backend, from `backend/`)
- Run: `uvicorn app.main:app --reload`
- Test: `pytest tests`
- Lint: `ruff check .`
