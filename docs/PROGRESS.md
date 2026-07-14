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

- [x] Pre-commit: `.pre-commit-config.yaml` (repo root) — rewritten to be portable (no
  absolute/machine-specific paths, works on any clone right after `pre-commit install`):
  - `pre-commit-hooks` (v6.0.0): trailing-whitespace, end-of-file-fixer, check-yaml,
    check-added-large-files, check-merge-conflict.
  - `ruff-pre-commit` (v0.15.21): `ruff --fix` + `ruff-format`, scoped to `backend/`.
    Both are pre-commit-managed (it downloads/pins its own ruff) — no dependency on this
    machine's Python at all.
  - `pytest` runs as a **pre-push** hook instead (`entry: pytest backend/tests`,
    `language: system`, `stages: [pre-push]`) — it needs the project's real dependencies
    (fastapi, sqlmodel, ...), which only exist in `backend/.venv`, so it relies on that
    venv being active on `PATH` at push time. Verified both ways: fails with "Executable
    `pytest` not found" when the venv isn't on `PATH`, passes when it is. CI is the real
    safety net regardless of local `PATH` state.
  - `backend/scripts/precommit_check.py` (the old absolute-path wrapper) deleted.
  - Reinstalled (`pre-commit install --hook-type pre-commit --hook-type pre-push`) and
    verified: `pre-commit run --all-files` → all green; `pre-commit run --hook-stage
    pre-push --all-files` → green with venv active.
- [x] CI: `.github/workflows/backend-ci.yml` — ruff + pytest on push/PR to `main`/`develop`,
  Ubuntu + Python 3.12, no secrets needed (db/auth tests mock `Settings`, never hit
  real Neon/Clerk).

- [x] Phase 1 started — `app/modules/subjects`: `models.py` (`Subject`, `owner_id`-scoped),
  `schemas.py` (`SubjectCreate`/`SubjectRead`, kept separate from the ORM model), `service.py`
  (create/list/get/delete, every query filtered by `owner_id`), `router.py` (thin — auth/DB
  wiring only), wired into `app/main.py`. First real Alembic autogenerate migration
  `74f229e49637_add_subjects_table` — applied to Neon, schema confirmed via
  `information_schema`. `tests/test_subjects.py` (5 tests): isolated in-memory SQLite +
  `app.dependency_overrides` for `get_session`/`get_current_user_id` (set up/torn down per
  test, not at import time, so nothing leaks into other test files); includes an explicit
  ownership-isolation test (one user can't see another's subjects).
- [x] **Bug found + fixed via live smoke test**: `app/core/auth.py` called
  `jwks_client.get_signing_key_from_kid(kid)` — that method doesn't exist on `pyjwt`
  2.13.0's `PyJWKClient` (real method: `get_signing_key(kid)`). `tests/test_auth.py`'s fake
  JWKS client had the same wrong method name, so unit tests passed while the real endpoint
  500'd on any malformed token. Caught by starting the real server against live Neon+Clerk
  and hitting `/subjects` with a bogus bearer token. Fixed in `auth.py`, and hardened the
  test: the fake is now built with `unittest.mock.create_autospec(PyJWKClient,
  instance=True)`, so calling a method that doesn't exist on the real class fails the test
  immediately instead of silently matching a drifted fake. Re-verified live: bad token now
  correctly returns 401.

## Next (Phase 1 — Core RAG)
- [ ] R2 bucket + upload endpoint
- [ ] Inngest ingest pipeline: chunk → Cohere embed → pgvector
- [ ] Ask endpoint: retrieve → Cohere Rerank → Claude (streaming)

## Blockers / needs from user
- Accounts + API keys needed for Phase 1: **Anthropic, Cohere, R2**. Inngest/Polar can wait
  until their respective features (jobs, billing) are actually built.
