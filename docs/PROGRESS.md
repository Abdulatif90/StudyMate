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

- [x] `app/modules/documents` (text-only — **no R2/Cohere/Inngest yet**, that's next):
  `models.py` (`Document` — `subject_id` FK, `owner_id`-scoped like `Subject`,
  `DocumentStatus` enum `pending`/`ready`/`failed`), `parsing.py` (PDF/DOCX/TXT text
  extraction, isolated behind one `DocumentParseError` regardless of the underlying
  library), `service.py` (ownership check via `subjects.service.get_subject`, then
  content-type + 20 MB size validation, then synchronous parse → `ready`/`failed`),
  `router.py` (`POST`/`GET /subjects/{subject_id}/documents`,
  `GET .../{document_id}`, thin exception→HTTP-status translation). Wired into
  `app/main.py`. Added `pypdf`, `python-docx`, `python-multipart` to `requirements.txt`.
  Migration `a3a3277e047c_add_documents_table`, applied to Neon.
  - **Enum storage gotcha caught before applying**: SQLAlchemy's `Enum` type defaults
    to storing a Python enum member's *name* (`'PENDING'`), not its *value*
    (`'pending'`) — confirmed empirically, then fixed with `values_callable` so the DB
    labels match what the JSON API actually returns (`'pending'`/`'ready'`/`'failed'`).
    Verified directly against Neon's `pg_enum` catalog.
  - `tests/test_documents.py` (9 tests): same isolated-SQLite pattern as
    `test_subjects.py`; covers upload+list+get, ownership isolation, 404s (missing
    subject and missing document), reject unsupported content-type (415), reject
    oversize file (413), and an unparseable "PDF" correctly landing as `status:
    failed` (not an error — the upload still succeeds, per the model's contract).
  - Live-verified end-to-end against real Neon (bypassing HTTP, since a real Clerk JWT
    needs a frontend that doesn't exist yet): created a subject + document through the
    real service layer, confirmed the status round-trips correctly through actual
    Postgres, then cleaned up the test rows (verified 0 left in both tables).

- [x] Chunking (text-only — **still no R2/Cohere/Inngest**, next increment):
  `chunking.py`: `chunk_text(text, chunk_size=1000, overlap=150) -> list[str]` — sliding
  window snapped back to the nearest paragraph/sentence/word boundary within a lookback
  range (falls back to a hard cut only when no boundary exists, e.g. one giant
  unbroken token). `DocumentChunk` model (`document_id` FK, `owner_id`-scoped like
  `Document`, `chunk_index`, `text`) — no embedding column yet, that's Cohere's turn.
  `service.create_document` now chunks the extracted text and inserts ordered
  `DocumentChunk` rows after a successful parse; `chunk_text("")` naturally returns
  `[]` for both a failed parse and a genuinely empty one (e.g. whitespace-only text
  file), so no special-casing was needed for "no chunks" — it falls out of the same
  code path. Added `service.list_chunks` (owner + document scoped, ordered by
  `chunk_index`) — no HTTP endpoint yet, not needed until Ask/RAG retrieval.
  Migration `19324f4f8f37_add_document_chunks_table`, applied to Neon.
  - `tests/test_chunking.py` (7 tests): pure algorithm tests — empty/whitespace-only →
    `[]`, short text → single chunk, long text splits with preserved order (verified via
    unique-per-sentence fixture + `.index()`, not exact-position assertions), consecutive
    chunks provably overlap, chunks land on sentence boundaries for realistic prose, and
    a single giant unbreakable token correctly falls back to a hard split.
  - `tests/test_documents.py` (+5 tests): chunk persistence on upload (single chunk for
    short text, multiple ordered chunks for long text), tenant scoping (`list_chunks`
    with the wrong `owner_id` returns nothing even for a real `document_id`), and both
    "no chunks" cases — an unparseable file (`status: failed`) and a whitespace-only
    one (`status: ready`, zero real content).
  - Live-verified against real Neon (service layer directly, same reason as the
    documents increment — no frontend yet for a real Clerk JWT): created a document
    with 200 sentences, confirmed 7 ordered, tenant-scoped chunks came back correctly,
    then cleaned up. Hit one non-issue along the way: manual cleanup script tried to
    delete a `Document` before its `DocumentChunk` rows and hit the FK constraint —
    expected, since no ORM-level `relationship()`/cascade exists (there's no `DELETE`
    endpoint yet, so this doesn't affect any real code path); fixed the script's
    delete order and confirmed zero rows left in all three tables afterward.
  Full suite: **34 passed**; `ruff check` → clean.

- [x] Embeddings (Cohere) + pgvector storage (**still no R2/Inngest**, next increment):
  `embedding.py`: `embed_texts(texts) -> list[list[float]]` via `embed-multilingual-v3.0`
  (1024-dim, `input_type="search_document"` — the future Ask endpoint must use
  `"search_query"` on its side, Cohere's retrieval quality depends on getting this
  asymmetry right), `batching=True` (the Cohere SDK itself splits large batches across
  requests — confirmed by inspecting `Client.embed`'s signature before relying on it).
  Two deliberately different failure modes: missing `COHERE_API_KEY` → bare
  `RuntimeError` at point of use (same as `db.py`/`auth.py` — a deploy mistake, not a
  per-document problem, so it fails loudly); any actual Cohere/network failure →
  `EmbeddingError` (caught by `service.py`, degrades to `status: failed`).
  `Settings.cohere_api_key` added; `.env.example` updated.
  - **`DocumentChunk.embedding`**: `pgvector`'s `Vector(1024)` — but SQLite (the whole
    test suite) has no vector type, so the column is
    `Vector(1024).with_variant(JSON(), "sqlite")`: real `vector` column on Postgres,
    plain JSON array on SQLite, same `list[float]` values either way. Verified this
    actually round-trips correctly against both a live SQLite engine *and* real
    Neon+pgvector with throwaway scratch tables before wiring it into the real model
    (found, along the way, that pgvector stores components as 4-byte floats — a
    `list[float]` round-tripped through real Postgres differs from the original at
    ~1e-16, pure float32 precision, not a bug; SQLite's JSON path has no such loss).
  - `service.create_document`: after chunking, calls `embed_texts` and stores one
    vector per chunk in the same transaction. `DocumentParseError`/`EmbeddingError` are
    caught together → `status: failed`, zero chunks persisted (extends the existing
    "failed → no chunks" invariant from the chunking increment to also cover embedding
    failures) — deliberately does **not** catch the missing-key `RuntimeError`, so a
    misconfigured deployment still fails loudly instead of masquerading as a
    per-document data problem.
  - Migration `b31b86c196ef_add_embedding_column_to_document_chunks`, applied to Neon.
    Autogenerate's rendered `pgvector.sqlalchemy.vector.VECTOR(...)` reference without
    importing `pgvector` (same class of gap as the earlier missing `import sqlmodel`)
    — fixed in the migration and added to `script.py.mako` so future migrations don't
    hit it either.
  - Tests, fully network-free (Cohere never actually called):
    `tests/test_embedding.py` (5) mocks the **Cohere client itself** — empty list never
    touches the client at all, a successful call's shape/args, API failures wrapped as
    `EmbeddingError`, a wrong-dimension response rejected, missing key raises
    `RuntimeError`. `tests/test_documents.py` (+4) mocks `embed_texts` instead, at the
    integration level — an embedding stored per chunk (with the right dimension),
    tenant-scoped (`list_chunks` for another owner sees nothing, including embeddings),
    an empty document still calls `embed_texts([])` (proving `service.py` doesn't
    special-case it — relies on `embed_texts`' own short-circuit instead) without
    reaching Cohere, and a forced `EmbeddingError` correctly lands the document at
    `status: failed` with zero chunks while the HTTP request itself still succeeds
    (201 — the *document* failed to process, the *request* didn't error).
  - Live-verified twice against the real stack: `embed_texts` directly against the
    real Cohere API (3 sentences → 3× 1024-dim vectors); then the full pipeline
    (`create_document` → parse → chunk → real Cohere embed → real Neon/pgvector store)
    end-to-end, confirmed the stored vector's dimension and values, then cleaned up
    (this time deleting chunks before their parent document, in FK order — see
    WORKLOG for the delete-ordering issue that came up during the *previous*
    increment's live test).
  Full suite: **43 passed**; `ruff check` → clean.

## Next (Phase 1 — Core RAG)
- [ ] R2 bucket + upload endpoint (store the actual file — right now only validated,
  not persisted anywhere)
- [ ] Ask endpoint: retrieve (pgvector similarity search) → Cohere Rerank → Claude
  (streaming) — embeddings now exist to retrieve against
- [ ] Inngest: move parsing/chunking/embedding off the request path into a background
  job (uploads currently do this synchronously, which is fine for small text files but
  won't scale to large PDFs or embedding API latency)

## Blockers / needs from user
- Accounts + API keys needed for Phase 1: **Anthropic, R2**. Inngest/Polar can wait
  until their respective features (jobs, billing) are actually built.
