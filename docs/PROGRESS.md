# PROGRESS

> Current state of the StudyMate build. **Read this to resume work** after any break/reset.

## Current phase
**Phase 0 — Setup: complete.** Next up: **Phase 1 — Core RAG** (Subjects, upload → R2 →
Inngest ingest, Ask/RAG, Conversations — see `docs/plan.md`).

## Done
- [x] Repo skeleton + `.gitignore`
- [x] Backend: FastAPI app + `/health` endpoint (`app/main.py`, `app/core/config.py`)
- [x] `.venv` + deps (fastapi, uvicorn, pydantic-settings) + dev (pytest, httpx, ruff)
- [x] First test `tests/test_health.py` — passing; ruff clean
- [x] Continuity docs: `CLAUDE.md`, `docs/{plan,PROGRESS,DECISIONS,WORKLOG}.md`
- [x] Git: `main` + `develop`; GitHub remote `origin` (Abdulatif90/StudyMate); both branches pushed

- [x] `app/core/db.py` — SQLModel engine/session (Neon), lazy `RuntimeError` if `DATABASE_URL`
  unset; `tests/test_db.py`
- [x] `app/core/auth.py` — Clerk JWT verification via JWKS (`PyJWKClient` + `pyjwt`),
  `get_current_user_id` FastAPI dependency; `tests/test_auth.py` (RSA keypair generated
  locally, no network calls)
- [x] `Settings` gained `database_url` / `clerk_jwks_url` / `clerk_issuer` (all optional —
  code raises a clear error at point of use, not at import time, so the app/tests still
  boot before accounts exist)
- [x] Ruff config: `extend-immutable-calls = ["fastapi.Depends"]` (stops false-positive B008
  on every FastAPI dependency)

- [x] User created Neon + Clerk accounts; real values in `backend/.env` (gitignored).
  Verified live: `get_engine()` connects to Neon (Postgres 18, `pgvector` extension enabled);
  `get_jwks_client()` fetches Clerk's real JWKS (1 signing key returned).

- [x] Alembic init (`backend/alembic/`): `env.py` reads `DATABASE_URL` from
  `app.core.config` (no connection string duplicated in `alembic.ini`); `target_metadata =
  SQLModel.metadata` (empty until Phase 1 domain models are imported there). First
  migration `fb44afd7a3d6_enable_pgvector_extension` — `CREATE EXTENSION IF NOT EXISTS
  vector`; applied to real Neon DB (`alembic upgrade head`), `alembic_version` confirmed.

- [x] Pre-commit: `.pre-commit-config.yaml` (repo root) — local hook running
  `backend/scripts/precommit_check.py` (ruff check + pytest) via `backend/.venv`'s own
  Python directly (entry uses an **absolute** path — `language: system` on Windows doesn't
  resolve a relative `entry` against pre-commit's cwd; a relative path silently fails with
  `WinError 2`). Installed (`pre-commit install`) and smoke-tested
  (`pre-commit run --all-files` → passed).
- [x] CI: `.github/workflows/backend-ci.yml` — ruff + pytest on push/PR to `main`/`develop`,
  Ubuntu + Python 3.12, no secrets needed (db/auth tests mock `Settings`, never hit
  real Neon/Clerk).

## Next (Phase 1 — Core RAG)
- [ ] `app/modules/subjects` — model + router + service (first domain module, first real
  Alembic autogenerate migration once it exists)
- [ ] R2 bucket + upload endpoint
- [ ] Inngest ingest pipeline: chunk → Cohere embed → pgvector
- [ ] Ask endpoint: retrieve → Cohere Rerank → Claude (streaming)

## Blockers / needs from user
- Accounts + API keys needed for Phase 1: **Anthropic, Cohere, R2**. Inngest/Polar can wait
  until their respective features (jobs, billing) are actually built.
