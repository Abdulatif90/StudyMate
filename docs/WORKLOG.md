# Worklog

Log of completed work (newest first). Each entry: what was done, tests, commit.

## 2026-07-14 — Phase 1 start: Subjects module + real auth bug found via live test
- First domain module, `app/modules/subjects/`: `models.py` (`Subject` — `id`, `owner_id`,
  `name`, `created_at`), `schemas.py` (`SubjectCreate`, `SubjectRead` — API shapes kept
  separate from the ORM model), `service.py` (create/list/get/delete, every query filtered
  by `owner_id` per CLAUDE.md rule 2), `router.py` (thin: just wires
  `Depends(get_session)`/`Depends(get_current_user_id)` to `service.py`, raises 404 via
  `HTTPException` when a subject isn't found or isn't owned by the caller). Registered in
  `app/main.py` via `app.include_router(subjects_router)`.
- Alembic: imported `Subject` in `alembic/env.py` so `SQLModel.metadata` (and therefore
  autogenerate) sees it. `alembic revision --autogenerate -m "add subjects table"` →
  `74f229e49637`. Had to hand-add `import sqlmodel` to the generated file — Alembic's
  autogenerate emits `sqlmodel.sql.sqltypes.AutoString()` for SQLModel string columns but
  doesn't import `sqlmodel` itself (a known SQLModel+Alembic gap). Added
  `import sqlmodel  # noqa: F401` to `script.py.mako` so future migrations don't hit the
  same missing-import bug (guarded with `noqa` since a raw-SQL-only migration, like the
  pgvector one, wouldn't actually use it and would otherwise fail `ruff check` on an
  unused import). Applied to real Neon (`alembic upgrade head`); confirmed the table
  schema via `information_schema.columns`.
- `tests/test_subjects.py` (5 tests): in-memory SQLite (`StaticPool` so all requests in a
  test share one connection) + `app.dependency_overrides` for `get_session` and
  `get_current_user_id`, set up and torn down by an `autouse` fixture (not at import time)
  so the overrides don't leak into other test files sharing the same `app` object. Covers
  create+list, 404 on missing subject, delete (+ 404 after), and — explicitly — that one
  owner's subjects are invisible to another (`test_subjects_are_scoped_to_owner`).
- **Live smoke test caught a real bug**: started the actual FastAPI app against the real
  `backend/.env` (live Neon + Clerk), hit `/subjects` with no token → correct 401, then
  with a garbage bearer token → **500**, not 401. Traceback: `app/core/auth.py` called
  `jwks_client.get_signing_key_from_kid(kid)`, but `pyjwt` 2.13.0's `PyJWKClient` has no
  such method — the real one is `get_signing_key(kid)`. `tests/test_auth.py`'s fake JWKS
  client had been hand-written with that same wrong method name, so it happened to match
  the buggy code instead of the real library and the unit tests passed anyway.
  - Fixed `auth.py` to call `get_signing_key`.
  - Hardened the test fixture: `_make_fake_jwks_client()` now builds the fake via
    `unittest.mock.create_autospec(PyJWKClient, instance=True)` instead of a hand-rolled
    class — `create_autospec` raises `AttributeError` for any method not on the real
    class, so a fake that drifts from the real API fails the test immediately instead of
    silently mirroring a bug.
  - Re-ran the live smoke test after the fix: bad token now correctly returns 401.
  - Lesson recorded here rather than just fixed silently: hand-written fakes/mocks for
    third-party clients need to be checked against the real API (or spec'd via
    `create_autospec`) — a fake that merely "looks plausible" can pass tests while hiding
    a broken integration.
- Full suite: **13 passed**; `ruff check` → clean; `pre-commit run --all-files` → clean.

## 2026-07-14 — Fix pre-commit portability (absolute venv path → managed hooks)
- Problem: `.pre-commit-config.yaml`'s `entry:` hardcoded this machine's absolute
  `backend/.venv` path, so it would break on any other clone.
- Rewrote it to use only portable, pre-commit-managed repos:
  `pre-commit/pre-commit-hooks` v6.0.0 (trailing-whitespace, end-of-file-fixer,
  check-yaml, check-added-large-files, check-merge-conflict) and
  `astral-sh/ruff-pre-commit` v0.15.21 (`ruff --fix` + `ruff-format`, both scoped to
  `files: ^backend/`). Pre-commit downloads/pins these tools itself — no reference to
  any local Python at all.
- Moved `pytest` out of the commit-time hook entirely: it needs the project's real
  dependencies (fastapi, sqlmodel, ...) which only live in `backend/.venv`, and there's
  no portable way to point a committed config at an arbitrary clone's venv. It's now a
  **pre-push** local hook (`entry: pytest backend/tests`, `language: system`, `stages:
  [pre-push]`) — relies on the venv being active on `PATH` at push time; CI remains the
  safety net when it isn't.
- Deleted `backend/scripts/precommit_check.py` (superseded — no longer needed now that
  ruff runs via pre-commit's own managed environment and pytest moved to pre-push).
- `pre-commit uninstall` then `pre-commit install --hook-type pre-commit --hook-type
  pre-push`.
- `ruff-format` reformatted one line in `alembic/env.py` (a call now fits on one line);
  `end-of-file-fixer` added a trailing newline to the Alembic-generated `README`. Both
  harmless, applied automatically.
- Verified: `pre-commit run --all-files` → all 7 hooks pass. `pre-commit run
  --hook-stage pre-push --all-files` → fails with "Executable `pytest` not found"
  without the venv on `PATH`, passes with it prepended (confirms the precondition is
  real and the hook behaves as designed either way). `ruff check .` and `pytest tests`
  from `backend/` → still **8 passed**, ruff clean.

## 2026-07-14 — Phase 0 complete: pre-commit hooks + CI
- `requirements-dev.txt`: added `pre-commit`.
- `backend/scripts/precommit_check.py`: runs `ruff check .` then `pytest tests -q` from
  `backend/`, using `sys.executable` (whichever Python launched it) so it stays in sync
  with `backend/.venv` without hardcoding a path inside the script itself.
- `.pre-commit-config.yaml` (repo root): one local hook, triggers only when a `backend/`
  file is part of the commit. `entry` had to be an **absolute** path to
  `backend/.venv/Scripts/python.exe` — a relative path failed with `WinError 2` because
  pre-commit's `language: system` on Windows resolves `entry` via PATH or as a literal
  absolute path, not relative to its cwd. (No usable system `python` exists on this
  machine's PATH — only a broken Microsoft Store alias — which is why the hook can't just
  bootstrap through a bare `python` command either.)
- Installed the hook (`pre-commit install`) and confirmed via
  `pre-commit run --all-files` → passed.
- `.github/workflows/backend-ci.yml`: ruff + pytest on push/PR to `main`/`develop`,
  Ubuntu + Python 3.12. Deliberately no `DATABASE_URL`/`CLERK_*` secrets configured — the
  test suite mocks `Settings` rather than hitting real Neon/Clerk, so CI needs none.
  Validated the YAML structure by parsing it with PyYAML.
- Phase 0 is now done end-to-end: FastAPI skeleton, Neon+pgvector, Clerk auth, Alembic,
  local pre-commit gate, CI. Next: Phase 1 (Subjects, upload/ingest, Ask/RAG).

## 2026-07-14 — Phase 0: Alembic init
- `requirements.txt`: added `alembic`.
- `alembic init alembic`; `alembic.ini` sqlalchemy.url left unset (no connection string
  duplicated in a committed file) — `env.py` reads `DATABASE_URL` from
  `app.core.config.get_settings()` instead, raising the same clear `RuntimeError` as
  `db.py`/`auth.py` if unset. `target_metadata = SQLModel.metadata`.
- `script.py.mako` template modernized (`from __future__ import annotations`, `X | Y`
  unions) so future auto-generated migrations pass ruff without hand-editing.
- First migration `fb44afd7a3d6_enable_pgvector_extension`: `CREATE EXTENSION IF NOT
  EXISTS vector` / `DROP EXTENSION IF EXISTS vector` — codifies what was done manually
  in the Neon SQL editor earlier, so a fresh Neon DB can be set up from migrations alone.
- Ran `alembic upgrade head` against the real Neon DB; confirmed `alembic_version` table
  recorded `fb44afd7a3d6`. Full test suite still **8 passed**; ruff clean.

## 2026-07-14 — Phase 0: Neon + Clerk accounts verified live
- User created real Neon + Clerk accounts and filled `backend/.env` (gitignored, uncommitted).
- Caught secrets pasted into `backend/.env.example` (tracked by git, unlike `.env`) before
  any commit — moved real values to `.env`, restored placeholders in `.env.example`.
  `git status` confirmed clean; `git log` confirmed the secrets were never committed/pushed.
- Verified live: `get_engine()` connects to Neon (Postgres 18.4, `pgvector` extension
  confirmed enabled); `get_jwks_client()` fetches Clerk's real JWKS (1 key returned).

## 2026-07-14 — Phase 0: db.py + auth.py (Neon + Clerk wiring)
- Guided Neon (Postgres + pgvector) and Clerk account setup (external — user-completed).
- `requirements.txt`: added `sqlmodel`, `psycopg2-binary`, `pyjwt[crypto]`.
- `app/core/config.py`: added optional `database_url` / `clerk_jwks_url` / `clerk_issuer`.
- `app/core/db.py`: cached SQLAlchemy engine (`pool_pre_ping=True`) + `get_session` FastAPI
  dependency. Raises `RuntimeError` if `DATABASE_URL` missing, only when actually used.
- `app/core/auth.py`: `PyJWKClient`-backed JWKS fetch/cache, `decode_clerk_token` (RS256 +
  issuer check), `get_current_user_id` dependency → 401 on missing/invalid token.
- Tests: `tests/test_db.py` (2), `tests/test_auth.py` (4) — all isolated from real
  credentials/network (fake settings via monkeypatch; locally-generated RSA keypair for JWT
  signing). Full suite: **8 passed**; `ruff check` → clean.
- `pyproject.toml`: `extend-immutable-calls = ["fastapi.Depends"]` — fixes bugbear B008
  false positive on FastAPI's standard `Depends(...)` default-arg pattern.
- `.env.example`: uncommented `DATABASE_URL` / `CLERK_JWKS_URL` / `CLERK_ISSUER` now that
  code reads them.

## 2026-07-14 — Phase 0: backend foundation
- Created repo skeleton, `.gitignore`, backend package (`app/`, `app/core`, `app/modules`,
  `app/shared`, `tests`).
- FastAPI app + `/health` endpoint (`app/main.py`); typed settings (`app/core/config.py`).
- Python 3.12 `.venv`; installed fastapi, uvicorn, pydantic-settings + dev tooling
  (pytest, httpx, ruff); `pyproject.toml` (pytest + ruff config).
- Test `tests/test_health.py` → **1 passed**; `ruff check` → clean.
- Continuity docs: `CLAUDE.md`, `README.md`, `docs/{plan,PROGRESS,DECISIONS,WORKLOG}.md`.
- Git: `main` + `develop` branches; commits `6e6ae33` (foundation), `7ee94b5` (push convention).
- GitHub: repo `Abdulatif90/StudyMate`; both branches pushed with upstream tracking.
