# PROGRESS

> Current state of the StudyMate build. **Read this to resume work** after any break/reset.

## Current phase
**Phase 0 — Setup** (in progress)

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

## Next (Phase 0 remainder)
- [ ] User: create Neon + Clerk accounts, fill real values into `backend/.env`
      (see `.env.example` — `DATABASE_URL`, `CLERK_JWKS_URL`, `CLERK_ISSUER`)
- [ ] Alembic init (needs real `DATABASE_URL` to run first migration against)
- [ ] pre-commit hooks (ruff + pytest) + CI workflow

## Blockers / needs from user
- Neon + Clerk accounts + real values in `backend/.env` (guided this session; I cannot create
  accounts or enter secrets myself).
- Accounts + API keys still needed later: **Anthropic, Cohere, R2, Inngest, Polar**.
