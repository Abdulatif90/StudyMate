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

## Next (Phase 0 remainder)
- [ ] **GitHub remote + push** (needs your GitHub auth — see below) — then push after every commit
- [ ] `app/core/db.py` — SQLModel engine/session (Neon)
- [ ] `app/core/auth.py` — Clerk JWT verification via JWKS
- [ ] Alembic init
- [ ] pre-commit hooks (ruff + pytest) + CI workflow

## Blockers / needs from user
- Accounts + API keys: **Neon, Clerk, Anthropic, Cohere, R2, Inngest, Polar** (user provides;
  I cannot create accounts or enter secrets).
