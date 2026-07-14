# Worklog

Log of completed work (newest first). Each entry: what was done, tests, commit.

## 2026-07-15 — Cohere embeddings + pgvector storage (still no R2/Inngest)
- User added `COHERE_API_KEY` to `backend/.env`. `requirements.txt`: added `cohere`,
  `pgvector`. `Settings.cohere_api_key: str | None = None`. `.env.example` uncommented
  the Cohere line.
- Before writing any code against it, installed `cohere` (7.0.5) and introspected it
  directly in the venv — same discipline that caught the `PyJWKClient` bug last
  increment. Findings that shaped the design:
  - `cohere.Client.embed(..., batching=True)` — the SDK itself splits large text
    batches across multiple requests; no manual chunking-into-batches needed on our
    side, just pass the flag.
  - No single `CohereError` base class is exported at top level; the real common base
    is `cohere.core.api_error.ApiError`, with `BadRequestError`/`UnauthorizedError`/etc.
    all inheriting from it — but since network-level failures (timeouts, DNS) might
    not even reach that hierarchy, `embed_texts` catches bare `Exception` around the
    API call and wraps it in `EmbeddingError`, the same pattern already used in
    `parsing.py` for third-party library exceptions.
  - Response shape depends on whether `embedding_types` is passed: omitted (our case)
    → `EmbeddingsFloatsEmbedResponse`, `.embeddings` is directly `list[list[float]]`.
    Confirmed by inspecting the Pydantic model fields directly rather than guessing.
- `app/modules/documents/embedding.py`: `embed_texts(texts) -> list[list[float]]` via
  `embed-multilingual-v3.0`, `input_type="search_document"` (the future Ask endpoint's
  query-side embedding must use `"search_query"` instead — Cohere's asymmetric model
  needs both sides right for retrieval to actually work). Missing API key → bare
  `RuntimeError` at point of use (config mistake, same as `db.py`/`auth.py`); any
  Cohere/network failure → `EmbeddingError` (a data-processing failure, handled
  gracefully by the caller). Validates response vector dimensions match
  `EMBEDDING_DIM` before returning, so a future model/config drift surfaces as a clear
  error here rather than a cryptic pgvector dimension-mismatch exception later.
  **Live-verified directly against the real Cohere API** (3 sentences, multilingual)
  before writing a single mocked test — confirmed 1024-dim vectors, confirmed the
  empty-list short-circuit never calls the API, confirmed the missing-key
  `RuntimeError` path.
- `DocumentChunk.embedding`: `pgvector.sqlalchemy.Vector(1024)` — but SQLite (the whole
  test suite's DB) has no vector type. Used `Vector(1024).with_variant(JSON(), "sqlite")`,
  SQLAlchemy's built-in mechanism for "use this type normally, but swap in a different
  one for a specific dialect." Did **not** trust this to just work — ran a throwaway
  script creating a real table with this column type against both a fresh SQLite engine
  and real Neon, inserting and reading back a `list[float]`, before touching the actual
  model. Both round-tripped correctly. Along the way, noticed the Neon round-trip
  doesn't come back byte-identical to the Python floats going in (~1e-16 max diff) —
  pgvector stores vector components as 4-byte floats, so this is plain float32
  precision loss, not a bug; worth remembering if anything ever asserts exact float
  equality against a real Postgres-stored vector (SQLite's JSON fallback has no such
  loss, since it's not actually a vector column).
- `service.create_document`: after chunking, calls `embed_texts` and stores one vector
  per chunk in the same transaction as the chunk rows. Catches
  `(DocumentParseError, EmbeddingError)` together → `status: failed`, zero chunks —
  extending the existing "failed → no chunks" contract from the chunking increment to
  also cover embedding failures, so `status: ready` still means exactly "chunks with
  embeddings exist," full stop. Deliberately does **not** catch the missing-key
  `RuntimeError` — see embedding.py's docstring for why. `zip(chunks_text, embeddings,
  strict=True)` when pairing them up, so a length-mismatched response from Cohere
  fails loudly instead of silently pairing the wrong vector with the wrong text.
- **Immediately re-ran the full test suite after wiring this in** (before writing any
  new mocks) specifically to check whether existing document-upload tests would now
  make real Cohere API calls — they would have. Added an autouse `_mock_cohere` fixture
  to `tests/test_documents.py` (patches `documents_service.embed_texts`) before
  proceeding any further, to avoid burning real API quota/cost during iteration.
- Alembic: same missing-import gap as `sqlmodel` before — autogenerate rendered
  `pgvector.sqlalchemy.vector.VECTOR(...)` in the migration without an `import
  pgvector.sqlalchemy` line. Fixed in the generated migration and added to
  `script.py.mako` so future migrations don't hit it either. Migration
  `b31b86c196ef_add_embedding_column_to_document_chunks` applied to Neon; confirmed the
  real column type is `vector` via `information_schema.columns`.
- Tests, fully network-free:
  - `tests/test_embedding.py` (5, new file): mocks `cohere.Client` itself (not our
    wrapper), so this actually exercises `embed_texts`' own logic — empty list never
    constructs a client at all, correct call shape/args for a real request, Cohere
    failures wrapped as `EmbeddingError`, a wrong-dimension response rejected, missing
    key raises `RuntimeError`.
  - `tests/test_documents.py` (+4): mocks `embed_texts` instead, at the integration
    level — an embedding is stored per chunk with the right dimension (and matches a
    deterministic fake scheme so tests can tell which vector came from which chunk);
    `list_chunks` for a different `owner_id` returns nothing (embeddings included,
    since the whole row is scoped); an empty/whitespace document still calls
    `embed_texts([])` — proving `service.py` relies on `embed_texts`' own short-circuit
    rather than special-casing empty input itself — via a `Mock(side_effect=...)` spy
    asserting the exact call; and a forced `EmbeddingError` correctly lands the
    document at `status: failed` with zero chunks while the HTTP response itself is
    still 201 (the *document* failed to process, the *request* didn't error).
- **Live-verified the full pipeline against the real stack**: `create_document` with a
  real short text, through real parsing → chunking → real Cohere embedding → real
  Neon/pgvector storage, confirmed the stored chunk's embedding dimension and sample
  values. Cleanup this time deleted `DocumentChunk` rows before their parent
  `Document` (in FK order) — the previous increment's live test hit exactly this
  ordering issue when cleaning up manually; fixed here from the start. Confirmed 0
  rows left in `subjects`, `documents`, and `document_chunks` afterward.
- Full suite: **43 passed** (9 new: 5 embedding unit tests + 4 documents integration
  tests); `ruff check` → clean.

## 2026-07-15 — Chunking (text-only; still no R2/Cohere/Inngest)
- `app/modules/documents/chunking.py`: `chunk_text(text, chunk_size=1000, overlap=150)`.
  Sliding window over character positions; each window's hard-cut end is nudged back
  to the nearest `\n\n` / sentence-ending punctuation / plain space within a 200-char
  lookback (`_find_boundary`), falling through to a hard cut only if nothing matches
  (e.g. one giant unbroken token — verified with a dedicated test). Overlap is applied
  by starting the next window `overlap` characters before the previous window's
  (boundary-adjusted) end, so a sentence split across a chunk boundary still appears
  whole in at least one chunk. `chunk_text("")` (after `.strip()`) returns `[]`.
  Verified the algorithm's actual behavior empirically (a throwaway script printing
  chunk positions/lengths against 200 unique numbered sentences) before writing formal
  assertions against it, rather than assuming the design would behave as intended.
- `DocumentChunk` model added to `documents/models.py`: `id`, `document_id` FK →
  `documents.id`, `owner_id` (same defense-in-depth duplication as `Document.owner_id`),
  `chunk_index`, `text`, `created_at`. No embedding column yet.
- `service.create_document`: after the existing parse step, now chunks the extracted
  text and inserts ordered `DocumentChunk` rows in the same transaction as the
  `Document` row. No special-casing needed for "failed parse" or "empty parse" — both
  naturally produce `text = ""` (or a parse that yields only whitespace), and
  `chunk_text("")` already returns `[]`, so the insert loop is just a no-op.
  `service.list_chunks(session, owner_id, document_id)` added for retrieval
  (owner + document scoped, ordered by `chunk_index`) — no HTTP endpoint yet, since
  nothing consumes chunks until the Ask/RAG endpoint exists.
- Alembic: imported `DocumentChunk` in `alembic/env.py` (technically already registered
  via the `Document` import from the same `models.py` file, but kept explicit for
  readability, matching the existing per-model-import convention). Migration
  `19324f4f8f37_add_document_chunks_table`, applied to real Neon; confirmed via
  `information_schema.columns`.
- Tests:
  - `tests/test_chunking.py` (7): empty/whitespace-only → `[]`; short text → single
    chunk; long text (200 unique numbered sentences) splits with source-order
    preserved (using `.index()` against unique content, not brittle exact-position
    assertions); consecutive chunks provably overlap
    (`positions[i+1] < positions[i] + len(chunks[i])`); chunks end on sentence
    boundaries for realistic prose; a single 500-char run of `"x"` (no boundary
    anywhere) correctly falls back to a hard split.
  - `tests/test_documents.py` (+5): a short upload produces exactly one chunk matching
    its content; a long upload produces multiple chunks in source order; chunks are
    owner-scoped (`list_chunks` with the wrong `owner_id` returns nothing even for a
    real `document_id`); an unparseable file (`status: failed`) produces no chunks;
    a whitespace-only text file (`status: ready`, but no real content) also produces
    no chunks — the two distinct "no chunks" paths named in the task both covered.
  - Chunks have no HTTP endpoint yet, so these tests read `DocumentChunk` rows
    directly via `service.list_chunks` against the same in-memory SQLite engine the
    `dependency_overrides` fixture already wires up — no new test infrastructure
    needed.
- Live-verified against real Neon (service layer directly — same reasoning as the
  documents increment: a real Clerk JWT needs a frontend that doesn't exist yet):
  created a document with 200 sentences, got back 7 correctly-ordered chunks, and
  confirmed a different `owner_id` sees zero chunks for the same `document_id`
  (genuine tenant-scoping check against actual Postgres, not just SQLite). Hit one
  non-issue while cleaning up test data: a manual `DELETE` script tried to remove the
  `Document` row before its `DocumentChunk` rows and hit the FK constraint (expected —
  no ORM-level `relationship()`/cascade is defined, and there's no `DELETE` endpoint in
  the app yet for this to actually matter). Fixed the cleanup script's delete order and
  confirmed 0 rows left in `subjects`, `documents`, and `document_chunks` afterward.
- Full suite: **34 passed** (12 new: 7 chunking + 5 documents); `ruff check` → clean.

## 2026-07-15 — Documents module (text-only; R2/Cohere/Inngest still to come)
- `app/modules/documents/`, mirroring the subjects module's layering:
  - `models.py`: `Document` (`id`, `subject_id` FK → `subjects.id`, `owner_id`,
    `filename`, `content_type`, `status`, `created_at`) and a `DocumentStatus` `StrEnum`
    (`pending`/`ready`/`failed`) — anticipates the future async Inngest pipeline
    (uploads will start `pending`, a job will resolve them), but for now (no async
    pipeline yet) `service.py` resolves straight to `ready`/`failed` synchronously.
  - `parsing.py`: `extract_text(content_type, raw) -> str` for PDF (`pypdf`), DOCX
    (`python-docx`), TXT (UTF-8 decode) — each library's own exceptions wrapped in one
    `DocumentParseError` so callers only handle one exception type regardless of
    format. The extracted text itself isn't persisted yet (nowhere to put it until
    chunking/embedding exists) — this increment only uses it to prove the file is
    genuinely readable.
  - `service.py`: `create_document`/`list_documents`/`get_document`, all owner-scoped.
    `create_document` order: (1) confirm the subject exists and is owned by the caller
    — reuses `subjects.service.get_subject`, since a document can never be more
    accessible than its parent subject — (2) reject unsupported content-type or a
    file over `MAX_UPLOAD_SIZE_BYTES` (20 MB), (3) attempt to parse, set `status`
    accordingly. Three distinct exceptions (`SubjectNotFoundError`,
    `UnsupportedFileTypeError`, `FileTooLargeError`) so the router's translation to
    404/415/413 is a simple 1:1 mapping instead of string-matching an error message.
  - `router.py`: `POST`/`GET /subjects/{subject_id}/documents` (nested path via
    `APIRouter(prefix=...)` with a path parameter in the prefix itself — FastAPI
    supports this directly) and `GET .../{document_id}`. Upload endpoint is `async def`
    (the only async route in the app so far) since `UploadFile.read()` is async;
    everything downstream (`service.py`, the DB session) stays synchronous, consistent
    with the rest of the codebase — accepted as fine at this project's scale, not
    something to fix by introducing an async DB driver now.
  - No `DELETE` endpoint yet — not required by this increment's scope, and deleting a
    document will need to account for R2 file cleanup once that exists; deferred.
  - `app/main.py`: `app.include_router(documents_router)`.
  - `requirements.txt`: added `pypdf`, `python-docx`, and `python-multipart` (FastAPI
    needs the latter for any multipart/file-upload endpoint — caught immediately by
    just importing `app.main`, before writing a single test).
  - `pyproject.toml`: `DocumentStatus(StrEnum)` triggered ruff's UP042 (prefer
    `enum.StrEnum` over `(str, Enum)` — already fixed by using `StrEnum` directly);
    `File(...)` as a route default triggered the same B008 false-positive as
    `Depends(...)` did in Phase 0 — extended `extra-immutable-calls` to include
    `fastapi.File`/`fastapi.Query`/`fastapi.Body` up front instead of hitting this
    once per FastAPI special-form parameter.
- **Caught before ever applying the migration**: SQLAlchemy's `Enum` type defaults to
  storing a Python enum member's *name* (`'PENDING'`), not its *value* (`'pending'`) —
  verified with a 3-line throwaway script (`SAEnum(DocumentStatus).enums` →
  `['PENDING', 'READY', 'FAILED']`) before trusting the autogenerated migration.
  Fixed with `sa_column=Column(SAEnum(DocumentStatus, values_callable=lambda cls: [e.value
  for e in cls]), nullable=False)` in `models.py`, deleted the not-yet-applied migration,
  and regenerated it — the new one correctly reads `sa.Enum('pending', 'ready',
  'failed', ...)`. Why this mattered: without the fix, the app would work fine end-to-end
  through the ORM (round-trip is internally consistent either way), but any future raw
  SQL against the `status` column — which this project does routinely for verification —
  would silently match nothing (`WHERE status = 'ready'` vs. actual stored `'READY'`).
- Alembic: imported `Document` in `alembic/env.py` alongside `Subject`. Applied
  `a3a3277e047c_add_documents_table` to real Neon; confirmed both the table columns
  (`information_schema.columns`) and the enum's actual stored labels
  (`pg_enum`/`pg_type`) are lowercase as intended.
- `tests/test_documents.py` (9 tests), same in-memory-SQLite + per-test
  `dependency_overrides` pattern as `test_subjects.py`: upload+list, get-by-id, 404 on
  missing subject (upload and list), 404 on missing document, ownership isolation
  (another user gets 404, not an empty list, since they don't own the subject either),
  415 on unsupported content-type, 413 on oversize file, and a garbage "PDF" correctly
  resulting in `status: failed` with a 201 (not an error response — the row is still
  created; only its status reflects the failure). Also fixed a `StarletteDeprecationWarning`
  along the way: `HTTP_413_REQUEST_ENTITY_TOO_LARGE` → `HTTP_413_CONTENT_TOO_LARGE`.
- **Live-verified against real Neon**, not just SQLite: since a real Clerk JWT needs a
  frontend that doesn't exist yet, verified the service layer directly (bypassing
  HTTP) — created a subject and a document through the real `service.py` functions
  against the live database, confirmed `DocumentStatus.READY` round-trips correctly
  through actual Postgres (not just information_schema inspection), then deleted both
  test rows and confirmed via `COUNT(*)` that zero rows were left behind in either
  table.
- Full suite: **22 passed**; `ruff check` → clean.

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
