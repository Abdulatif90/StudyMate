# PROGRESS

> Current state of the StudyMate build. **Read this to resume work** after any break/reset.

## Current phase
**Phase 0 — Setup: complete.** **Phase 1 — Core RAG: complete.** **Phase 2 — Quiz + FTS
hybrid: complete.** **Phase 3 — Flashcards + SM-2: complete.** **Phase 4 — Progress
tracking complete (backend + frontend); billing complete on the backend (entitlement layer
+ Polar checkout/webhook, SANDBOX).** Progress is a read-only `app/modules/progress/` plus
a per-subject page and an overall `/dashboard`. `app/modules/billing/` holds an entitlement
layer — Free/Pro/Business plans and enforced usage caps — plus the Polar wiring that feeds
it: `POST /billing/checkout` (authenticated) and a public, signature-verified
`POST /billing/webhook` whose *only* job is upserting one `UserPlan` row. The entitlement
layer itself stays provider-agnostic. **Nothing is blocked on keys any more**; the one open
item is confirming the webhook against a real Polar delivery (needs a `polar listen`
tunnel — see Blockers), and Polar is sandbox-only so far. The **billing frontend** is now
done too — a `/billing` page (plan + usage meters + upgrade→Polar-checkout) plus a 402
upgrade prompt on subject-create — leaving only the browser click-through and the real
webhook delivery open. Phase 1–3 recap: Subjects, documents
(R2 + Inngest ingest with auto-summary, deletable), hybrid Ask/RAG (Postgres FTS + vector
+ RRF + Cohere Rerank, streaming), Conversations, Quiz (tool-use generation + full UI),
Flashcards + SM-2 (tool-use generation + full review-session UI) — all with their own
frontends already shipped.

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

- [x] Retrieval — `service.search_chunks` (no HTTP endpoint yet; still no Claude/R2/Inngest):
  `embed_query(text) -> list[float]` added to `embedding.py` (`input_type="search_query"`
  — the retrieval half of the asymmetry `embed_texts`/`"search_document"` started;
  both now share a private `_embed(texts, input_type)` to avoid duplicating the
  try/except + dimension-check logic). `search_chunks(session, owner_id, subject_id,
  query, top_k=8)`: embeds the query, then `ORDER BY embedding <=> :query_vec LIMIT
  top_k` via pgvector's `cosine_distance()` comparator (confirmed it maps to `<=>` by
  reading `Vector.comparator_factory`'s source before using it), filtered by
  `owner_id AND subject_id AND embedding IS NOT NULL`. Returns `list[tuple[DocumentChunk,
  float]]`, `float` = `1 - cosine_distance` (higher = more similar).
  - **`DocumentChunk.subject_id` added** (denormalized from `Document`, same reasoning
    as the existing `owner_id` duplication): lets retrieval filter by owner+subject
    directly on the hot query path, no join. Confirmed `document_chunks` was still
    empty on Neon before adding it `NOT NULL` directly (no backfill needed). Migration
    `ba1acb6a4b7c_add_subject_id_to_document_chunks`, applied.
  - **Dialect-branches on `<=>`**: it only exists on Postgres, so off it (the SQLite
    test engine) `search_chunks` still applies every WHERE filter but skips the
    similarity ordering/scoring entirely (returns `0.0` for every score) — confirmed
    via `session.get_bind().dialect.name` before relying on it. This is what makes the
    scoping logic unit-testable on SQLite at all; real ranking is Postgres-only.
  - **Real bug caught by the first SQLite scoping test**: a chunk created with
    `embedding=None` was still coming back from `embedding IS NOT NULL`. Root cause:
    SQLAlchemy's `JSON` type (the SQLite variant fallback) stores Python `None` as the
    literal text `"null"` (JSON null), not a real SQL `NULL`, unless told otherwise —
    confirmed via `typeof(embedding)` returning `'text'` instead of `'null'` for that
    row. Fixed with `JSON(none_as_null=True)`; Postgres's real `Vector` type never had
    this problem (a `None` there is already a genuine column `NULL`).
  - Tests: `tests/test_embedding.py` (+2, `embed_query`'s call shape/args and error
    wrapping, Cohere client mocked). `tests/test_search.py` (new, 5 tests): SQLite-only
    scoping (owner+subject match required, a sibling subject's chunks excluded, a
    different owner's chunks excluded even under the same subject name, chunks
    without embeddings excluded, `top_k` respected, missing subject raises
    `SubjectNotFoundError`) — Cohere mocked, network-free. Plus one **live integration
    test against real Neon**, `@pytest.mark.skipif` on `not
    get_settings().database_url` (not a raw `os.getenv` check — that wouldn't see
    `.env`-file-only values): creates 3 real documents on different topics, real
    Cohere embeddings throughout, asserts a photosynthesis-themed query actually
    ranks the photosynthesis document first with descending similarity scores —
    genuine semantic-ranking verification, not just plumbing. (Originally this ran
    automatically whenever `DATABASE_URL` was set, hitting real Neon+Cohere on every
    local `pytest`/pre-push — fixed in the very next increment below with an explicit
    `live` marker.)
  - Caught my own test-helper bug along the way, distinct from the production bug
    above: `_make_chunk(embedding=None)` was silently replaced by the helper's default
    vector, because `if embedding is None: embedding = <default>` can't distinguish
    "caller didn't pass this" from "caller explicitly passed `None`". Fixed with a
    proper `_UNSET` sentinel default instead of `None`.
  Full suite: **50 passed** (7 new); `ruff check` → clean.

- [x] Test-infra fix — gate live tests behind an explicit `pytest -m live` opt-in.
  Problem: the live Neon+Cohere test from the retrieval increment ran on *every*
  `pytest`/pre-push (it only checked `DATABASE_URL` being set, which it is in this
  dev environment), making the "default" test run silently network-dependent again.
  `pyproject.toml`: registered a `live` marker (`markers = ["live: hits real
  Neon/Cohere, opt-in"]`) and set `addopts = "-m 'not live'"` so the default run
  always deselects it. `tests/test_search.py`'s live test gained
  `@pytest.mark.live` (kept the existing `skipif` on `DATABASE_URL` too, so
  `pytest -m live` still skips cleanly rather than erroring in an environment with
  no real DB configured at all). Verified both invocations directly: plain `pytest`
  → **49 passed, 1 deselected** (fast, offline); `pytest -m live` → **1 passed, 49
  deselected** (hits real Neon+Cohere). Confirmed Neon left clean (0 rows in all
  three tables) after the `-m live` run.

- [x] Ask endpoint — `POST /subjects/{subject_id}/ask` (RAG, non-streaming; SSE is a
  follow-up). New domain module `app/modules/ask/` (per CLAUDE.md's planned structure:
  router + service + schemas, no models — Ask doesn't persist anything of its own).
  - `llm.py`: `ask_claude(question, chunks) -> str` via `claude-haiku-4-5-20251001`.
    System prompt: answer only from provided excerpts, cite `(filename, chunk N)`,
    match the question's language, refuse plainly when excerpts don't cover it.
    Missing `ANTHROPIC_API_KEY` → bare `RuntimeError` at point of use (same pattern as
    `db.py`/`auth.py`/`embedding.py`); any Claude API/network failure → `LLMError`.
    `Settings.anthropic_api_key` added; `.env.example` updated.
  - `service.ask_question`: `search_chunks` (already built) → `get_documents_by_ids`
    (new batched owner-scoped lookup in `documents/service.py`, for citing filenames)
    → `ask_claude`. **All graceful degradation lives here, not the router**: empty
    retrieval and a Claude failure both return a normal 200 `AskResponse` with an
    explanatory `answer` and empty `sources`, rather than an HTTP error — the only
    exception that reaches the router is `SubjectNotFoundError` (from `search_chunks`
    itself), translated to 404.
  - `router.py`: thin, just the 404 translation. Wired into `app/main.py`.
  - Live-verified `ask_claude` directly against the real Anthropic API before writing
    any tests: confirmed the citation format `(filename, chunk N)` appears in real
    output, confirmed it refuses an unrelated question instead of answering from
    outside knowledge, confirmed it responds in Spanish to a Spanish question.
  - Tests: `tests/test_llm.py` (3, Anthropic client mocked directly — call
    shape/system-prompt/response-parsing, error wrapping, missing-key
    `RuntimeError`). `tests/test_ask.py` (5 SQLite + 1 live): answer+sources returned
    with the right context actually passed to Claude; 404 for a missing subject and
    for another owner's subject; empty-material and Claude-failure cases both
    gracefully degrade (200, explanatory answer, empty sources) instead of erroring.
    On SQLite, `search_chunks` never calls Cohere at all (see the retrieval
    increment), so only document upload needed Cohere mocked here — the ask flow
    itself only needed Claude mocked. Live test (`@pytest.mark.live`, `skipif` on
    `DATABASE_URL`) runs the real pipeline end-to-end — real Neon storage, real
    Cohere embeddings (both sides), real Claude generation — and asserts the answer
    is actually grounded (not a refusal) with the right source file cited.
  Full suite: **59 passed** (8 new: 6 in default run + 2 live), `ruff check` → clean.

- [x] Conversations (multi-turn chat history for Ask). `app/modules/ask/models.py`
  (new): `Conversation` (`subject_id` FK, `owner_id`, `title?`, `created_at`) —
  one conversation belongs to exactly one subject — and `ConversationTurn`
  (`conversation_id` FK, `owner_id`, `question`, `answer`, `sources` as JSON,
  `created_at`). `sources` stores what was actually shown at the time (filename,
  chunk index, text, similarity score) rather than re-deriving it later, since the
  underlying chunks could change (re-embedded, deleted) after the fact.
  - `AskRequest` gains optional `conversation_id`; `AskResponse` gains
    `conversation_id` (always present — a new conversation is created when none is
    given). `documents.service._require_owned_subject` renamed to public
    `require_owned_subject` (dropped the underscore) so `ask.service` can reuse the
    exact same ownership check before creating/loading a conversation.
  - `service.ask_question`: verifies subject ownership, then either loads the given
    conversation (verifying it's both owned by the caller **and** belongs to this
    subject — a conversation from a different subject 404s, not silently mixes
    context) or creates a new one. Loads that conversation's full history via
    `list_turns`, caps it to the most recent `MAX_CONTEXT_TURNS` (10) for what
    actually gets sent to Claude, then **always** saves a `ConversationTurn` —
    including both graceful-degradation paths (no relevant material, Claude failure)
    — since the chat transcript should show what was actually asked and answered
    either way, not just the successful cases.
  - `llm.ask_claude` gains `prior_turns`: built as real prior turns in Claude's
    native multi-turn `messages` list (alternating user/assistant), not stuffed into
    the system prompt — idiomatic use of the Messages API for conversation
    continuity. Only the *current* question carries retrieved excerpts; earlier
    turns carry just their original question/answer.
  - New endpoints: `GET /conversations` (owner-scoped list), `GET
    /conversations/{id}` (with full turn history), `DELETE /conversations/{id}`
    (optional per the task, included for CRUD completeness). Two `APIRouter`s in
    `ask/router.py` now (different prefixes — one can't serve both
    `/subjects/{id}/ask` and `/conversations`), both wired into `app/main.py`.
  - Migration `ee395363541a_add_conversations_and_conversation_turns_tables`.
    Caught before applying: `ConversationTurn.sources` came out of autogenerate as
    nullable, but it should never actually be `NULL` (always a list, possibly
    empty) — tightened to `Column(JSON, nullable=False)`, deleted and regenerated
    the not-yet-applied migration. Applied to Neon; confirmed via
    `information_schema.columns`.
  - **Real bug, caught by the live end-to-end test, in production code this time
    (not just a test cleanup script)**: `service.delete_conversation` deleted every
    turn, then the conversation, in that order — but hit the exact same
    FK-ordering surprise as the earlier Document/DocumentChunk cleanup issue,
    because there's still no ORM-level `relationship()`/cascade (consistent with
    this codebase's plain-FK-column style everywhere else), so SQLAlchemy's flush
    doesn't know the deletes are order-dependent. Fixed with an explicit
    `session.flush()` between the turn deletes and the conversation delete —
    forces the child deletes to actually hit the DB before the parent delete is
    even attempted. Re-ran the live test to confirm the fix, not just reasoned
    about it.
  - Tests: `tests/test_ask.py` (+10 default, live test extended): a follow-up
    question reuses the same conversation and the *exact* prior Q&A is asserted in
    the `prior_turns` argument passed to the (mocked) `ask_claude` call; a
    conversation from a different subject 404s; turns are saved even when there's
    no relevant material or Claude fails (both asserted by re-fetching the
    conversation and checking its transcript, not just the immediate response);
    `GET`/`DELETE /conversations` are owner-scoped (404 for another owner, empty
    list for another owner). Live test extended with a real follow-up turn in the
    same conversation (confirms `conversation_id` stays stable and both turns
    persist), using `delete_conversation` itself for cleanup — which is exactly
    what surfaced the FK-ordering bug above.
  Full suite: **69 passed** (10 new default + existing 2 live extended),
  `ruff check` → clean.

- [x] CORS: `CORSMiddleware` added to `app/main.py`, allowing the frontend's origin
  to call the API cross-origin. `Settings.cors_origins` — comma-separated (not
  JSON), defaults to `http://localhost:3000` — with a `cors_origin_list` property
  splitting it; comma-separated instead of pydantic-settings' usual JSON-for-lists
  requirement, since that's more friction than this needs. `tests/test_cors.py` (3):
  the split itself, an allowed origin gets the CORS header, a disallowed one doesn't.

- [x] Frontend scaffolded — first working end-to-end slice (Clerk sign-in → FastAPI
  JWT verification → real DB write), closing the loop Phase 1 has been building
  toward. `frontend/`: Next.js 15 (App Router, TS, Tailwind).
  - `@clerk/nextjs`: `ClerkProvider` in `app/layout.tsx`, `clerkMiddleware` in
    `middleware.ts` protecting `/subjects(.*)`, `/sign-in` and `/sign-up` pages.
  - Typed API client: `openapi-typescript` generates `lib/api/schema.d.ts` from the
    live backend's `/openapi.json` (`npm run generate-api-types`); `lib/api/client.ts`
    wraps it with `openapi-fetch`. `lib/api/useApiClient.ts` attaches the caller's
    Clerk session token as `Authorization: Bearer` on every request via an
    `openapi-fetch` middleware (registered once per mount via a ref, so token
    refreshes are picked up without re-registering).
  - `@tanstack/react-query` (`Providers` in `app/providers.tsx`) for data
    fetching/mutation state.
  - shadcn/ui, **Base UI variant** (not Radix) — `components/ui/{button,card,input,
    label}.tsx`. Caught one real issue: Base UI's `Button` defaults to
    `nativeButton={true}` and warns loudly in the console when rendered as something
    other than a real `<button>` (here, as a `next/link` via the `render` prop, on the
    homepage's two CTA buttons) — fixed by passing `nativeButton={false}` alongside
    `render`.
  - First protected page, `/subjects` (`app/subjects/page.tsx`): list + create,
    using the typed client + React Query end-to-end.
  - `frontend/.gitignore` bug caught before committing: its blanket `.env*` pattern
    was also swallowing `.env.local.example` (the committed template, same role as
    `backend/.env.example`) — added `!.env*.example` so the template stays tracked
    while real `.env`/`.env.local` files stay ignored.
  - **Live-verified the full stack together for the first time**: started
    `uvicorn` + `npm run dev`, signed in through the real Clerk UI, created a subject
    through the `/subjects` page, confirmed FastAPI's `get_current_user_id`
    (JWKS-based) verified the real Clerk-issued JWT and the row landed in Neon —
    the first real confirmation that Clerk (frontend) and Clerk (backend JWKS/issuer
    config) are actually the same app end-to-end, not just independently configured.
  - Backend: 70 passed (3 new CORS tests), `ruff check` → clean. Frontend:
    `tsc --noEmit` clean, `eslint` clean.

- [x] Frontend: Subject detail page (`/subjects/[subjectId]`) — list + upload
  documents, the second frontend increment.
  - `app/subjects/[subjectId]/page.tsx`: client component reading the dynamic
    segment via `useParams()` (consistent with `/subjects` already being a client
    component — no server/client split needed just for this). `GET
    /subjects/{subject_id}` for the name, `GET /subjects/{subject_id}/documents`
    for the list, both via the typed client + React Query.
  - Upload: a native `<input type="file">` (shadcn `Input`, which already forwards
    arbitrary `<input>` props/ref) drives a `useMutation` that builds a `FormData`
    and calls `POST /subjects/{subject_id}/documents`. **openapi-fetch multipart
    workaround**: the generated request-body type is `{ file: string }` (
    `openapi-typescript` renders OpenAPI's `format: binary` as `string`, it has no
    `File`/`Blob` type), but `openapi-fetch`'s default `bodySerializer` passes a
    `FormData` instance straight through to `fetch` untouched (confirmed by
    reading its source before relying on it — `defaultBodySerializer` checks
    `body instanceof FormData` first) and the browser sets the multipart
    `Content-Type` boundary itself. So the real `FormData` is built by hand and
    passed as `body`, cast to the generated (technically wrong, but
    openapi-typescript's known limitation) `{ file: string }` type. On success,
    invalidates the documents query so the list refreshes.
  - Upload states: `uploadDocument.isPending` disables the input and shows a
    "processing" note (uploads are still synchronous end-to-end — parse → chunk →
    Cohere embed — so this can take a few seconds, matching the backend's current
    architecture, not yet Inngest-backed). Errors read the response's real HTTP
    status (`response.status`, not the typed `error` shape — the OpenAPI schema
    only documents 201/422 for this route, since FastAPI doesn't auto-document
    hand-raised `HTTPException`s, so 404/415/413 aren't in the generated types even
    though the backend does return them) and map 415/413 to friendly messages;
    anything else falls back to a generic "couldn't upload" message.
  - Each document shown with filename + a status `Badge` (added via `npx shadcn add
    badge`, matching the existing Base-UI-variant components): default (ready),
    destructive (failed), secondary (pending).
  - `/subjects/page.tsx`: each subject card now links to its detail page. Already
    covered by the existing `/subjects(.*)` middleware matcher — no route
    protection change needed.
  - **Live-verified past just "shows ready" in the UI**: after the user confirmed
    upload + ready status in the browser, queried Neon directly (service layer,
    same reasoning as every other live check this project does) — confirmed the
    uploaded PDF actually produced 34 `DocumentChunk` rows, each with a real
    1024-dim Cohere embedding, not just a document row that happened to flip to
    `ready`.
  - Frontend: `tsc --noEmit` clean, `eslint` clean (one unused-import warning
    caught and fixed before commit). Backend unchanged this increment (no new
    endpoints — reused `GET .../documents` and `POST .../documents`, both already
    existed and tested).

- [x] Frontend now has a real test suite (CLAUDE.md rule 4 gap closed — the two
  frontend increments above had shipped on manual `tsc`/`eslint`/browser checks
  only, no automated tests). `vitest` + `@vitejs/plugin-react` + `jsdom` +
  `@testing-library/react` + `@testing-library/jest-dom`; `vitest.config.ts`
  (jsdom, resolves `@/` → `./src`), `vitest.setup.ts` (imports
  `@testing-library/jest-dom/vitest` — the plain, non-Vitest-specific entry point
  needs a Jest-style global `expect` Vitest doesn't provide). `npm run test` /
  `test:watch` scripts. Extracted the Subject-detail page's two pure helpers into
  `lib/uploadError.ts` (`friendlyUploadError`) and `lib/documentStatus.ts`
  (`documentStatusVariant`) so they're independently testable; 8 tests total
  (both helpers' branches + a `Badge` render smoke test proving the
  component-testing path works for later pages). Also fixed while in the file:
  `onError` now resets the file input too (previously only `onSuccess`, so
  retrying the same file after a transient failure silently no-op'd — browsers
  don't re-fire `onChange` for reselecting an unchanged input value), the
  documents `.map()` param renamed `document` → `doc` (was shadowing the global
  `document`), and a 404/unowned subject now shows "Subject not found" and
  returns early instead of still rendering the upload card underneath it.
  `tsc --noEmit` clean, `eslint` clean.

- [x] Frontend: `docs/FRONTEND.md` (responsive + semantic-color-token rules for every
  page/component) and CLAUDE.md rule 7 requiring it, then a full responsive + brand-color
  pass across the pages that predate the rule: `globals.css` gained an indigo/blue
  `--primary`/`--ring` (was grayscale) in both light and dark; home, `/subjects`,
  `/subjects/[subjectId]`, sign-in, and sign-up all moved to mobile-first padding
  (`p-4 sm:p-8`), and the subject detail page's title/filename rows now wrap/truncate
  instead of overflowing on narrow screens.

- [x] Frontend: Ask/RAG chat UI + conversations list (`/subjects/[subjectId]/ask`) —
  the last open Phase 1 frontend page; backend for both already existed.
  - **Layout**: sidebar (new-conversation button, conversations grouped by date via
    `groupConversationsByDate`, each with a truncated preview from its first question
    via `truncateText` and a delete button) + main transcript + compose box, following
    `docs/FRONTEND.md` (mobile-first, sidebar collapses above the transcript on narrow
    screens, semantic tokens only).
  - `lib/conversationFilter.ts`: `GET /conversations` is owner-scoped across every
    subject, so the sidebar filters to just this one client-side.
  - Sidebar previews fetch full turn history for *every* listed conversation up front
    (`useQueries`, not just the active one) — gives each item a real first-question
    preview like Claude's own sidebar, and makes clicking one instant since its turns
    are already loaded.
  - `QuestionMessage`/`AnswerMessage` (`components/`): question bubbles support
    copy/edit/delete; answer bubbles render markdown (`react-markdown`, headings
    downgraded to keep visual hierarchy inside a chat bubble), support copy/pin/
    read-aloud (`speechSynthesis`), and run answer text through
    `lib/simplifyCitations.ts` to drop the noisy `chunk N` suffix from inline
    citations while keeping the filename. Both action rows are right-aligned
    (timestamp above, icon buttons below) per user feedback during live testing.
  - **Edit & resend** ("regenerate from here"): the backend has no per-turn edit/delete,
    only whole-conversation CRUD, so editing a question drops it and everything after
    it from the visible transcript, then resends with the same `conversation_id`.
    `lib/editTurn.ts` (`splitTurnsAtEdit`, extracted+tested after this exact split logic
    caused a real bug below) does the split; the removed turns are held in a ref and put
    back if the resend fails, rather than discarded — otherwise a failed edit/resend
    silently dropped the question with no way to recover it.
  - **Pending state**: a "Sending…" bubble stands in for the in-flight question (new
    ones and edit-resends both), and the compose form itself is hidden entirely while a
    request is in flight (matching the reference UX of Claude's own chat input) instead
    of staying visible in a disabled state — three live-testing bugs fixed together
    here: the pending bubble briefly coexisting with the just-finished real turn (now
    cleared in the same `onSuccess`/`onError` state update, not a separate `onSettled`),
    the compose box still showing the just-typed text while its bubble also showed it
    below (now cleared on submit, restored only if the send actually fails), and the
    emptied box's placeholder looking like a reset/error rather than "sent".
  - Tests (all pure helpers/components, matching this codebase's established
    page-untested/helpers-tested pattern — `tsc`/`eslint`/live-browser-verified for the
    page itself): `conversationFilter.test.ts`, `editTurn.test.ts` (5 — split point at
    start/middle/end/not-found/empty-list), `groupConversationsByDate.test.ts`,
    `relativeTime.test.ts`, `simplifyCitations.test.ts`, `truncateText.test.ts`,
    `question-message.test.tsx`, `answer-message.test.tsx`.
  - `vitest.setup.ts` gained an explicit `afterEach(cleanup)` — needed once tests
    started using `@testing-library/user-event` across multiple `it()`s in the same
    file; without it, DOM from earlier tests in a file stuck around and caused
    "multiple elements found" failures in later ones. `@testing-library/user-event`
    added as a dev dependency for this.
  - **Live-verified in the browser** (user-driven, iterative): four real UX bugs found
    by hand-testing the pending/edit flow — all described above — were fixed in this
    session, not caught by any test beforehand (page-level interaction bugs, not pure-
    logic ones; the extracted `splitTurnsAtEdit` now covers the one piece of this that
    *is* pure logic).
  Frontend: `tsc --noEmit` clean, `eslint` clean, **37 passed** (11 test files).

- [x] Streaming: converted the Ask endpoint to SSE (explicitly deferred twice before this).
  Non-stream `POST /subjects/{subject_id}/ask` kept as-is; new `POST
  .../ask/stream` (`text/event-stream`) added alongside it.
  - **Event shape** (documented in `service.py` next to where it's produced):
    zero or more `event: token` / `data: {"text": "<delta>"}`, then exactly one
    terminal `event: done` / `data: {"conversation_id", "turn_id", "sources"}`.
  - `llm.ask_claude_stream`: same system prompt, `prior_turns` handling, and
    `(filename, chunk N)` citation contract as `ask_claude` — both now share a
    `_build_messages` helper so they can't drift apart. Uses
    `client.messages.stream(...)`, yields `stream.text_stream` deltas. Being a
    generator function, its body (including the missing-key `RuntimeError`)
    doesn't run until first iterated — covered explicitly by a test, since it's
    an easy assumption to get wrong.
  - `service.py` split into `prepare_ask_stream` (ownership/conversation/
    retrieval — an ordinary call, raises `SubjectNotFoundError`/
    `ConversationNotFoundError` synchronously) and `stream_answer` (the actual
    generator). Split was required, not stylistic: a `StreamingResponse`'s
    status code is locked in the moment its body starts iterating, so a 404
    raised from inside the generator would be too late to ever reach the
    client as a real 404 — router.py calls `prepare_ask_stream` in a normal
    `try/except` before constructing the `StreamingResponse` at all.
  - **Persistence — exactly once, only after the stream resolves**: `stream_answer`
    accumulates deltas locally and calls `create_turn` as its literal last
    action, after the token loop fully resolves — normally, via the no-material
    path, or via a caught `LLMError`. Never per-delta, never with partial text.
    LLM failure has two sub-cases: nothing generated yet → the same
    `_GENERATION_FAILED_ANSWER` fallback as the non-stream path (sources: []);
    failed partway through → keeps the real partial text and its sources rather
    than appending a confusing "try again" after genuine grounded output.
  - **Client-abort behavior, decided and documented in `stream_answer`'s
    docstring**: if the client disconnects mid-stream, the generator is torn
    down before reaching the persistence step (which only ever runs with the
    *complete* answer, never a partial one), so no half-written turn is
    possible. If the client merely navigates away without an immediate
    disconnect signal, generation keeps running server-side and the turn still
    gets saved — same behavior as Claude.ai/ChatGPT's own chat UIs. There is no
    code path that persists a truncated/inconsistent record.
  - Tests: `tests/test_llm.py` (+4: deltas yielded, wraps a failure before any
    delta, wraps a failure partway through — partial deltas already yielded are
    still observed via `next()` before the error, missing-key `RuntimeError`
    only surfaces on first iteration not at call time).
    `tests/test_ask.py` (+9 default, mirroring the non-stream suite one-for-one
    — token/done events, both 404s, no-material, LLM-failure-before-any-delta,
    LLM-failure-partway-through persists the partial answer, turn-saved-even-
    when-no-material, follow-up reuses conversation + prior context, 404 for a
    conversation from a different subject — plus 1 live test parsing real SSE
    output end-to-end against real Neon+Cohere+Claude). A small `_parse_sse`
    test helper decodes the raw `event:`/`data:` body back into pairs.
    Backend: **83 passed** (26 new), `ruff check` → clean.
  - Frontend: `EventSource` can't attach the Clerk bearer token (GET-only, no
    custom headers), so `lib/api/streamAsk.ts` uses `fetch()` + a manual
    `ReadableStream` reader instead, attaching the token the same way
    `useApiClient`'s middleware does. `lib/parseSSE.ts` (`createSSEParser`) is
    the one genuinely pure piece — an incremental parser that buffers a partial
    event/line across arbitrary `ReadableStream` chunk boundaries — pulled out
    specifically so it has direct unit tests (6, incl. an event split across
    three chunks) rather than only being exercised through the page.
  - `ask/page.tsx`: replaced the `askQuestion` mutation with `startAsk`, driving
    `streamAsk` directly; the old `pendingQuestion` string became a `streaming
    { question, answer }` object so the same in-flight state drives both the
    pending question bubble and a new live-filling `AnswerMessage` (new
    `streaming` prop — hides copy/pin/read-aloud on not-yet-complete text)
    below it. Preserved from the non-stream version: edit/resend still uses
    `splitTurnsAtEdit`, and the removed turns still get restored if the resend
    fails. Added: an `AbortController` per stream, aborted on unmount and on
    switching/starting a conversation mid-stream (server-side generation and
    persistence continue regardless, per the backend's documented abort
    behavior above — this only stops updating a component that's moved on);
    editing a *different* turn while one is already streaming is now a no-op
    instead of allowing two concurrent asks.
  - `AnswerMessage` gained a `streaming` prop (test: partial text renders,
    action row hidden while streaming; actions reappear once it's false).
  - **Live-verified** against real Neon+Cohere+Claude at two levels:
    1. Service-layer pytest live test (same reasoning as every other live test
       here — no real Clerk JWT outside a browser): real tokens streamed in,
       the `done` event's sources non-empty and grounded, persisted turn's
       answer matching the streamed text exactly.
    2. **HTTP transport level** — the one thing TestClient can't prove, since it
       buffers the whole SSE body. Ran the real app under `uvicorn` on a real
       socket (auth dependency overridden, since no real Clerk JWT is available
       here — everything else real: Neon + Cohere + Claude), then hit
       `/ask/stream` with an `httpx` streaming client and timestamped each raw
       wire chunk: 3 chunks arrived spread over 0.72s (t≈3.77s → 4.00s →
       4.49s), i.e. genuinely incremental off the socket, not one buffered
       blob. Answer came back grounded with an inline `(cell.txt, chunk 0)`
       citation and one source in `done`. Neon left clean afterward. (Throwaway
       verification script, not committed.)
  - **Still needs a manual browser pass** with real Clerk auth: token-by-token
    rendering in the actual React UI, sources appearing, edit-and-resend over
    the stream, and switching conversations mid-stream aborting the client view
    while the turn still persists. The transport-level streaming underneath all
    of these is now verified (above); what's unverified is only the React
    wiring, which needs a browser (none available in this environment).
  - Frontend: `tsc --noEmit` clean, `eslint` clean, **45 passed** (13 files).
  Note: a pre-existing local `uvicorn --reload` dev server was found running
  during this work serving stale code (missing the new route) — needs a manual
  restart before the browser pass.

- [x] Inngest: moved document processing (parse → chunk → Cohere embed → persist) off
  the request path into a background job. Upload now returns `pending` immediately; the
  job resolves it to `ready`/`failed`. (The `Document.status` enum already existed for
  exactly this.)
  - **Config/wiring**: `inngest>=0.5` dependency; `Settings.inngest_event_key` /
    `inngest_signing_key` (optional, so the app/tests boot without them);
    `app/core/inngest_client.py` holds the one shared client + `require_event_key()`
    (bare `RuntimeError` at point of use if the key's unset — same loud-failure
    pattern as db.py/embedding.py/llm.py, so events can't silently vanish leaving
    documents stuck on `pending`). `.env.example` documents both vars.
  - **service.py split**: `create_document` is now sync/on-request — validate
    ownership + content-type + size, insert a `pending` row, return. The heavy work
    moved to `process_document` (the job's target). `enqueue_document_processing`
    emits the `document/uploaded` event. `documents/jobs.py` is the thin Inngest
    function (pulls ids off the event, opens a session, calls `process_document`,
    wrapped in one `ctx.step.run` for retry durability); `app/main.py` serves it at
    `/api/inngest` via `inngest.fast_api.serve`.
  - **Idempotency (Inngest retries on failure)**: `process_document` deletes any
    chunks from a prior attempt before re-inserting, and no-ops if `raw_content` is
    already cleared (a retry after a successful-but-unacked run) — a retried
    parse+embed can't leave duplicate `DocumentChunk` rows. Preserves the old
    invariant: `DocumentParseError`/`EmbeddingError` → `status: failed`, zero chunks
    (never left stuck on `pending`); a missing `COHERE_API_KEY` still raises loudly
    (RuntimeError) rather than masquerading as a per-document failure.
  - **Where the bytes live** (interim, **since replaced by R2 — see the R2 entry
    below**): the job runs in a *separate* request (Inngest calls back over HTTP), so
    it needs the file bytes from a shared store, but there was no file store yet and an
    Inngest event can't carry a 20 MB PDF. A temporary nullable `documents.raw_content`
    (BYTEA) column stashed the bytes until the job consumed them. Migration
    `7877073ae76d`. This column was removed once R2 landed.
  - **Frontend**: the subject-detail page now polls the documents list while any
    document is `pending` (`lib/documentsPolling.ts` → `documentsRefetchInterval`,
    TanStack Query `refetchInterval`), so a badge flips pending → ready/failed on its
    own; polling stops once all are settled. Upload copy updated (upload is fast now;
    processing is background). Chose to add polling here rather than defer it —
    otherwise the async change would silently break the upload UX (docs would sit on
    `pending` forever without a manual refresh).
  - Tests: `test_documents.py` restructured — upload tests assert `pending` + that the
    event was enqueued + that nothing was processed on the request path; the
    parse/chunk/embed assertions moved to tests that call `process_document` directly,
    plus idempotency (retry-after-success no-op, retry-after-partial delete-then-reinsert
    → no dupes) and a missing-document no-op. `test_inngest.py` (new): missing-key
    RuntimeError + the event-send shape. `test_ask.py`/`test_search.py` updated to
    `process_document` after `create_document` (their live tests need the chunks).
    Backend: **89 passed** (3 deselected live), `ruff` clean. Frontend:
    `documentsPolling.test.ts` (4); **49 passed** (13 files), `tsc`/`eslint` clean.
  - **Live-verified end-to-end** against real Neon + Cohere + the real Inngest Dev
    Server (`npx inngest-cli dev`): started the app + dev server, uploaded a document
    through the real HTTP API → response was `pending` immediately → the Inngest job
    (dev server callback → `process_document` → real Cohere embed → Neon) resolved it
    to `ready` in ~3s with 1 chunk persisted. Also ran the `-m live` suite (3 passed —
    `create_document`+`process_document` against real Neon/Cohere/Claude). Neon left
    clean. (Throwaway scripts, not committed.) Not browser-tested with real Clerk auth
    — the poll/badge UX still wants a manual pass.

- [x] R2 (Cloudflare, S3-compatible) file storage — uploaded files now persist to R2
  instead of the interim `documents.raw_content` BYTEA stash (which is removed).
  - `app/core/r2_client.py`: one shared boto3 S3 client against
    `https://<account_id>.r2.cloudflarestorage.com` (built once, same pattern as
    `inngest_client.py`); `put_object`/`get_object`/`delete_object` +
    `build_object_key`. Missing/partial R2 creds → `R2ConfigError` (a `RuntimeError`)
    at point of use, listing exactly which vars are missing — same loud-failure
    pattern as db.py/embedding.py/llm.py/inngest_client. `Settings` gains
    `r2_account_id`/`r2_access_key_id`/`r2_secret_access_key`/`r2_bucket_name`
    (optional so the app/tests boot without them); `.env.example` documents all four;
    `boto3>=1.34` added.
  - **Owner-scoped keys**: `build_object_key(owner_id, document_id, filename)` →
    `{owner_id}/{document_id}/{filename}`. The owner prefix namespaces tenants; the
    document_id makes it unique per upload. Ownership is still verified at the DB layer
    (`require_owned_subject` / `get_document_by_id` are owner-scoped) *before* R2 is
    ever touched — the key isn't itself an authz check, just a derived path.
  - `service.create_document`: after validating (incl. the 20 MB limit — **before**
    the upload, never upload-then-reject), builds the row + key and uploads to R2
    *before* committing the pending row, so a failed upload leaves nothing persisted
    (no pending row pointing at a missing object). `process_document`: fetches the
    bytes from R2 (`r2_object_key`) instead of the old column. `models.py`:
    `r2_object_key` column added, `raw_content` removed. Migration
    `4220579b8fb6_swap_documents_raw_content_for_r2_key`, applied to Neon (confirmed
    the column swap via `information_schema`).
  - **Object lifecycle**: the R2 object is **kept** after processing (R2 is the file
    store now, not a temp stash) — it stays available for re-processing and future
    "download original". Idempotency invariant is intact: `process_document` still
    deletes prior-attempt chunks before re-inserting, so re-running (Inngest retry,
    now re-fetching the same bytes from R2) never duplicates chunks. No delete-document
    endpoint exists yet, so nothing deletes objects — that's not a *new* leak (one
    object per document), and a future delete endpoint should call
    `r2_client.delete_object`. Parse/embed failures still → `status: failed`; an R2
    fetch failure (like a missing Cohere key) raises loudly and lets Inngest retry
    rather than masquerading as a per-document `failed`.
  - Tests: `test_r2_client.py` (new) — key builder (owner-scoped, no cross-owner
    collision), `R2ConfigError` when any of the four creds is missing (parametrized),
    put/get/delete call boto3 with the right Bucket/Key, plus a **live** round-trip
    (`-m live`) that puts/gets/deletes a real object through the real bucket and
    confirms the delete. `test_documents.py`/`test_ask.py`/`test_search.py` gained an
    in-memory R2 fake (autouse) so the default suite stays offline; new document tests
    assert the upload stores the file under the owner-scoped key and that the object is
    kept after processing. Backend **97 passed** (4 deselected live), `ruff` clean.
  - **Live-verified end-to-end** twice: (1) the `-m live` suite (4 passed, incl. the
    real-R2 round-trip); (2) the full real pipeline against the real Inngest Dev Server
    + real R2 + real Neon/Cohere — HTTP upload → file confirmed present in **real R2**
    immediately (95 bytes) → `pending` → Inngest job fetched it back from real R2 →
    `ready` in ~1.5s with 1 chunk. R2 object + Neon rows cleaned up; confirmed 0 test
    objects left in the bucket. (Throwaway scripts, not committed.)

- [x] DELETE document endpoint — `DELETE /subjects/{subject_id}/documents/{document_id}`.
  Closes the object-lifecycle gap the R2 increment left open (files were never removed
  once uploaded).
  - `service.delete_document(session, owner_id, subject_id, document_id) -> bool`:
    owner+subject scoped (same lookup as `get_document`, so a non-owner gets a 404 and
    can't even detect the document exists), returns `False` when not found/not owned
    → router 404. `router.py`'s `DELETE` route mirrors `ask.router`'s
    `delete_conversation` pattern exactly (`if not service.delete_document(...): raise
    404`, `204 No Content`).
  - **Order, decided and documented in the docstring**: `DocumentChunk` rows are
    deleted and flushed *before* the `Document` row (no ORM `relationship()`/cascade in
    this codebase — same flush-before-parent-delete fix already applied twice before,
    in the Document/DocumentChunk and `delete_conversation` cleanups). The **R2 delete
    happens after the DB delete has committed**, not before: if the DB delete were to
    fail/roll back after an R2 delete already succeeded, a `Document` row would be left
    pointing at a now-missing object — deleting R2 second avoids that. Once the DB
    delete has committed, there's no longer any row to "point at" anything, so the R2
    delete afterward is best-effort: its exceptions are caught and logged, not
    re-raised — `delete_object` is idempotent, and a transient R2 failure at that point
    only leaves a harmless orphaned object (storage-cost debt, not a dangling
    reference), and must not turn an already-successful deletion into a 500.
  - A `None` `r2_object_key` (a legacy row from before that column existed) is handled
    — the R2 delete step is simply skipped, not attempted against a `None` key.
  - Tests (offline, `test_documents.py`): removes chunks + R2 object + row; deleting a
    still-`pending` document (no chunks yet) works cleanly; 404 for a missing document,
    a missing subject, another owner's document (and confirms it's left completely
    untouched — still fetchable by the real owner, chunks intact, R2 object intact),
    and a document from a different subject; tolerates a simulated R2 failure (204
    still returned, DB row still gone) and a `None` r2_object_key. Plus a **live** test
    (`-m live`) that deletes a real document and confirms the object is actually gone
    from the real bucket (`ClientError`/`NoSuchKey`), not just that the DB row is gone —
    the offline suite's R2 fake is skipped for `@pytest.mark.live` tests specifically so
    this one exercises the real `r2_client` functions. Backend **105 passed** (5
    deselected live), `ruff` clean.
  - **Live-verified end-to-end** twice: (1) the `-m live` suite (5 passed, incl. the new
    real-R2-delete test); (2) the full real HTTP flow against the real app — upload →
    file confirmed present in real R2 → `DELETE` → `204` with an empty body → `GET`
    afterward → `404` → object confirmed gone from real R2 (`NoSuchKey`) → re-`DELETE`
    (already gone) → `404`. Neon left clean afterward. (Throwaway script, not
    committed.)
- [x] Frontend: delete-document button on the subject-detail page — the delete
  endpoint's last missing piece; **closes out Phase 1 Core RAG entirely**.
  - Cleaned up a stray uncommitted one-line edit already sitting in this file
    (`break-words` → `wrap-break-word`, both valid/equivalent Tailwind) that predated
    this increment and wasn't part of it — discarded rather than folded in, since
    there was no evidence it was an intended, in-progress change.
  - `lib/api/schema.d.ts` regenerated (`npm run generate-api-types` against the
    running backend) — the DELETE route (and, it turned out, `/ask/stream` and
    `/api/inngest` from earlier increments) weren't in the typed client yet.
    `api.DELETE("/subjects/{subject_id}/documents/{document_id}", ...)` is now typed.
  - A destructive-variant icon button per document row (`variant="destructive"` —
    already a semantic-token variant in `components/ui/button.tsx`, matches
    `docs/FRONTEND.md`'s "destructive token for the delete affordance"), `Trash2`
    icon, `window.confirm` guard — same pattern as the ask page's existing
    conversation-delete. A `useMutation` calls the typed DELETE; **checks `error`, not
    `data`** (the 204 response leaves `data` undefined, which is not a failure —
    exactly the pitfall called out for this increment). On success, invalidates
    `["subjects", subjectId, "documents"]`, so the row disappears and the existing
    `documentsRefetchInterval` polling keeps working unchanged (same query key, no
    changes to that hook). Per-row pending state via
    `deleteDocument.isPending && deleteDocument.variables === doc.id`, so deleting one
    document doesn't disable every row's button. **Not** gated on document status — a
    still-`pending` document can be deleted too (the backend already allows this; the
    button has no status check to accidentally block it).
  - `lib/deleteError.ts` (`friendlyDeleteError`): maps a 404 (already deleted/not
    found) to a specific message, same shape as the existing `friendlyUploadError`;
    2 tests.
  - Verified: `tsc --noEmit` clean, `eslint` clean, `npm run build` (production build)
    succeeds, **51 passed** (14 files, up from 49/13). Not click-tested in a real
    browser — no browser or real Clerk auth available in this environment; the
    backend endpoint itself was already live-verified end-to-end (real HTTP → real R2
    → real Neon) in the increment that added it, and this call is a thin, typed
    wrapper mirroring the already-proven `deleteConversation` pattern on the ask page.

- [x] Auto-summary on document upload — closes a Phase 1 gap (`docs/plan.md`'s ingest
  step is "chunk → Cohere embed → pgvector + auto-summary"; auto-summary had never
  actually been built despite Phase 1 being marked complete).
  - `Document.summary: str | None` (nullable). `documents/summarization.py` (new):
    `summarize_document(text) -> str` via Claude (`claude-haiku-4-5-20251001`), same
    Anthropic SDK/error pattern as `ask/llm.py` — multilingual (responds in the
    excerpt's own language), input capped at 12,000 chars (a background-job step, not
    worth summarizing a full 20 MB upload), missing `ANTHROPIC_API_KEY` → bare
    `RuntimeError`, any API failure → `SummarizationError`.
  - `service.process_document`: after a successful chunk+embed, generates and stores
    the summary — **best-effort**, unlike the parse/embed step before it: a
    `SummarizationError` is caught/logged and leaves `summary` NULL rather than
    failing the document (still resolves `ready` with its chunks intact). A missing
    API key still raises loudly, same as the missing-Cohere-key case.
  - `DocumentRead` gained `summary`; subject-detail page shows it (muted text) under
    each `ready` document.
  - Migration `35c81d01e21d_add_summary_column_to_documents`, applied to Neon,
    confirmed via `information_schema`.
  - Tests: `test_summarization.py` (4, offline, Anthropic client mocked directly).
    `test_documents.py` (+3): summary written on success, left NULL on a forced
    `SummarizationError` (chunks still intact, still `ready`), left NULL on a parse
    failure. Plus 1 live test against real Claude. Backend **112 passed** (6
    deselected live), `ruff` clean. Frontend: `tsc`/`eslint` clean, `npm run build`
    succeeds, **51 passed** (14 files).
  - **Live-verified end-to-end** three ways: the `-m live` suite (6 passed, Neon
    confirmed clean afterward); the full real pipeline — real HTTP upload (auth
    dependency overridden, no real Clerk JWT available outside a browser) against the
    real app + real Inngest Dev Server + real R2/Cohere/Claude — `pending` → `ready`
    in ~4s with a genuine Claude-generated summary, then cleaned up via real `DELETE`
    calls, Neon confirmed clean afterward. Not click-tested in a real browser (no
    browser/Clerk auth available in this environment — same standing gap as every
    other frontend page here).

- [x] Cohere Rerank in the Ask retrieval path — closes the last Phase 1 gap
  (`docs/plan.md`'s Ask line is "retrieve → Cohere Rerank → Claude"; the Rerank step
  had never actually been built).
  - `documents/rerank.py` (new): `rerank(query, texts, top_n) -> list[(index,
    relevance_score)]` via `rerank-v3.5` (Cohere's multilingual rerank model — same
    multilingual reasoning as `embed-multilingual-v3.0`). Reuses
    `embedding._get_client` (one Cohere `Client` supports both `.embed()` and
    `.rerank()`) rather than duplicating the `COHERE_API_KEY` check. Confirmed the
    real SDK signature/response shape by introspecting the installed package and a
    real one-off call before writing any code against it. Any API/network failure →
    `RerankError`.
  - `service.search_chunks`: on the Postgres path, retrieves a **wider**
    vector-similarity candidate pool (`RERANK_CANDIDATE_POOL = 30`, same
    owner/subject/embedding-NOT-NULL filters — widening only changes the `LIMIT`),
    then a new `_rerank_candidates(query, candidates, top_k)` helper reranks and cuts
    down to `top_k` — only that final set reaches Claude, never the wider pool.
    `_rerank_candidates` is pure Python over an already-fetched list (no DB/dialect
    dependency) — directly unit-testable regardless of Postgres vs. SQLite. SQLite
    branch (the whole offline suite) untouched — no vector ordering to rerank there.
  - **Graceful degradation, decided in `_rerank_candidates`'s docstring**: a
    `RerankError` must not break Ask (which already degrades gracefully everywhere)
    — falls back to the pre-rerank vector-similarity order truncated to `top_k`,
    same best-effort spirit as the auto-summary step above. `SourceChunk
    .similarity_score` now means Cohere's `relevance_score` on the reranked path, or
    raw cosine similarity on the fallback — documented since both mean "higher is
    more relevant" but aren't on the same scale.
  - `ask/service.py`/`prepare_ask_stream` needed no changes — both already call
    `search_chunks` as the shared entry point.
  - Tests: `test_rerank.py` (new, 6, Cohere client mocked directly — call shape,
    index/score mapping, `top_n` capping, API-failure wrapping, and one test proving
    the `COHERE_API_KEY` check is genuinely reused from `embedding.py`, not
    duplicated). `test_search.py` (+4, `_rerank_candidates` pure-logic tests: reorder
    by relevance score, `top_k` respected, `RerankError` falls back to vector order,
    empty-candidates short-circuit). Existing live semantic-ranking test extended in
    place to exercise the real rerank path. Backend **121 passed** (6 deselected
    live, up from 112/6), `ruff` clean.
  - **Live-verified end-to-end** two ways: the `-m live` suite (6 passed, Neon
    confirmed clean); the full real pipeline — 4 real documents (2 on-topic, 2
    off-topic) processed through the real service layer, then a real HTTP
    `POST /subjects/{id}/ask` (auth dependency overridden) — real Cohere Rerank
    scores clearly separated on-topic (0.75, 0.72) from off-topic (0.03, 0.02)
    chunks, answer grounded with correct citations from both on-topic documents.
    Cleaned up via real `DELETE` calls; Neon confirmed clean afterward.

## Phase 2 — Quiz
- [x] Quiz generation via Claude **tool-use structured output** (DECISIONS.md #5 — quiz
  JSON from a validated tool call, never `json.loads` on prose). First structured-output
  integration in the codebase. New domain module `app/modules/quiz/` (router + service +
  schemas + models + generation, same established split as documents/ask).
  - `models.py`: `Quiz` (subject_id FK, owner_id-scoped, title?) + `QuizQuestion`
    (quiz_id FK, owner_id, question, options as NOT-NULL JSON, correct_index,
    explanation?, order). Plain FK columns, no ORM cascade — so `delete_quiz` flushes
    question deletes before the parent (the flush-before-parent rule that bit
    Document/DocumentChunk, `delete_conversation`, `delete_document` before). Migration
    `5ffe4bd447ff_add_quizzes_and_quiz_questions_tables`, applied to Neon, confirmed via
    `information_schema` (`options` is NOT NULL).
  - `generation.py`: `generate_quiz_questions(excerpts, num_questions)` forces Claude
    (`claude-haiku-4-5-20251001`) to call a strict `record_quiz` tool via `tool_choice`,
    then reads the structured `tool_use` block's `.input` back out — confirmed the exact
    tool-use API shape (`tools=[{name,description,input_schema}]`, `tool_choice`,
    `.content[i].type == "tool_use"` → `.input`) by introspecting the installed
    anthropic SDK + a live one-off call before writing any code. Defensive validation
    turns any malformed/empty response into `QuizGenerationError` — notably an
    out-of-range `correct_index` (schema-valid integer, but would silently break a
    future grading flow) and a bool masquerading as an int. Missing `ANTHROPIC_API_KEY`
    → bare `RuntimeError` at point of use (db.py/llm.py pattern); multilingual (writes
    in the source material's language, like summary/ask).
  - `service.py`: `generate_quiz` verifies subject ownership, samples the subject's
    material (new `documents.service.sample_subject_chunk_texts` — a broad owner+subject
    chunk-*text* sample, selecting only the text column so no embeddings load and no
    Cohere call happens, evenly strided for coverage; reuses existing retrieval, no
    re-embedding), generates via tool-use, and persists Quiz + questions in one
    transaction (nothing persisted unless generation fully succeeds — no orphaned empty
    quiz on failure). Plus list/get (owner+subject scoped) and delete_quiz.
  - `schemas.py` **answer-key decision, documented**: this generation+review increment
    has no graded-submission flow, so the read shapes intentionally reveal
    `correct_index`/`explanation` (self-study tool, owner-scoped — you quiz yourself on
    your own material). A future graded flow must NOT reuse `QuizQuestionRead` for the
    "take" step — add a separate answer-hidden shape and reveal only post-submission.
    `owner_id` never exposed.
  - `router.py`: `POST` (generate, 201), `GET` list, `GET` one, `DELETE` one — thin,
    mirroring documents/ask. Exception→status: `SubjectNotFoundError`→404,
    `NoQuizMaterialError`→422 (subject has no processed chunks yet),
    `QuizGenerationError`→502. Wired into `app/main.py`. Frontend `schema.d.ts`
    regenerated (quiz route types now in the typed client; no consumer yet — the quiz
    UI is the next increment).
  - Tests: `test_quiz_generation.py` (10, Anthropic client mocked directly — tool schema
    + forced tool_choice sent, tool_use parsed back, every malformed-response path →
    `QuizGenerationError`, empty-excerpts short-circuit, missing-key `RuntimeError`).
    `test_quiz.py` (19 SQLite integration + 1 live, generation mocked at the service
    boundary offline): persists quiz+questions in order with no `owner_id` leak; 404
    unowned/missing subject, 422 no material, 502 generation failure (nothing persisted
    on failure); num_questions passthrough + request bounds (0/21 → 422); list/get
    owner+subject scoping and cross-subject 404s; delete removes quiz + its questions,
    404s for missing/another-owner/different-subject and leaves them intact. Backend
    **150 passed** (7 deselected live, up from 121/6), `ruff` clean.
  - **Live-verified end-to-end** two ways: the `-m live` quiz test (real Neon + Cohere +
    Claude tool-use → well-formed questions, in-range `correct_index`, cleaned up); and
    the **full real stack** — real Inngest Dev Server + real R2/Neon/Cohere/Claude —
    real HTTP upload (auth dependency overridden, no Clerk JWT outside a browser) →
    `pending` → Inngest job → `ready` (summary populated) in ~4s → `POST /quizzes` →
    4 well-formed MCQs from real Claude tool-use, each with an in-range correct answer →
    `GET` re-fetched the persisted quiz → list returned the summary shape. Cleaned up via
    real `DELETE`s; Neon confirmed clean afterward (0 rows across all five tables).
    Not click-tested in a real browser (no browser/Clerk auth here — same standing gap
    as every frontend page); the quiz frontend is the next increment anyway.

- [x] Quiz frontend — generate, take (self-test), review, delete. Consumes the typed
  `/subjects/{id}/quizzes` routes; follows the established page pattern (client
  component, `useApiClient` + TanStack Query, shadcn Base-UI, `docs/FRONTEND.md`).
  - `app/subjects/[subjectId]/quizzes/page.tsx`: lists the subject's quizzes (title or
    "Untitled quiz" + relative time, each links to its take view) and a generate form
    (optional title + `num_questions` 1–20, default 5). Generate guards against
    double-submit (`disabled` + `isPending` check) and shows a "Generating…" state
    (it's a live Claude round-trip); 422 (no processed material — actionable
    "upload/wait" message) and 502 (retryable) mapped via `friendlyQuizError` off the
    real `response.status` (not in the typed error shape). Delete mirrors the
    delete-document flow (`window.confirm`, destructive icon, checks `error` not
    `data` since 204 → `data` undefined, invalidates on success).
  - `app/subjects/[subjectId]/quizzes/[quizId]/page.tsx`: take/review view. Options are
    selectable buttons; **`correct_index` is never used to style anything until the
    user reveals** (held client-side, compared only on "Check answers"), so it's a real
    self-test, not an answer sheet. "Check answers" is gated by `allAnswered` (every
    question answered). On reveal: score (`scoreQuiz`), each correct option marked with
    the `--success` token + a check icon, a wrong pick with the `destructive` token + an
    x icon (color always paired with an icon, per FRONTEND.md), explanations shown, and
    a "Try again" reset. Options lock once revealed.
  - Subject-detail page: a "Quizzes" (outline) button next to the existing "Ask" button.
  - Pure logic extracted + unit-tested (helpers-tested / pages-verified-live pattern):
    `lib/quizError.ts` (`friendlyQuizError` — 422/502/other, 3 tests) and
    `lib/quizScore.ts` (`allAnswered`/`isCorrect`/`scoreQuiz` — 11 tests, incl. a
    selected index of 0 counting as answered, unanswered counting as incorrect).
  - New semantic token: `--success`/`--success-foreground` (OKLCH, both light+dark,
    registered in the `@theme inline` map) — added per FRONTEND.md's "add `--success`
    when needed" rather than hardcoding green, so correct answers use `bg-success/10
    text-success border-success`.
  - `schema.d.ts` unchanged (quiz routes were already regenerated into it in the
    backend increment — no hand-edits).
  - Verified: `tsc --noEmit` clean, `eslint` clean, **65 passed** (16 files, up from
    51/14), `npm run build` succeeds (both new routes compile:
    `/subjects/[subjectId]/quizzes` and `.../quizzes/[quizId]`). Not click-tested in a
    real browser (no browser/Clerk auth in this environment — same standing gap as every
    other frontend page here); the quiz *API* it drives was already live-verified
    end-to-end through the real stack in the backend increment, and `tsc` guarantees the
    UI consumes those exact typed shapes.

- [x] Hybrid retrieval — Postgres full-text (FTS) + vector, fused with Reciprocal Rank
  Fusion (RRF), then Cohere Rerank. Closes Phase 2 (DECISIONS.md #4 — FTS lives in
  Postgres, not rebuilt in Python per query).
  - **FTS in Postgres**: migration `066f42dbed80` adds `document_chunks.text_search_vector`
    as a `GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED` column + a GIN index.
    Generated/stored → computed once per row on write and **auto-populated for existing
    rows by the ALTER** (no separate backfill); regenerates when `text` changes. `'simple'`
    config: no language-specific stemming/stopword removal (right for multilingual
    material) and IMMUTABLE (required for a generated column — the 1-arg `to_tsvector`
    is only STABLE and can't be used). Managed in **raw SQL, not on the `DocumentChunk`
    model**, so the SQLite test engine (no tsvector) can still `create_all`;
    `alembic/env.py` gained an `include_object` that excludes this Postgres-only
    column/index from autogenerate so a future `--autogenerate` never proposes dropping
    it (verified: `alembic check` → "No new upgrade operations detected"). Applied to
    Neon, confirmed via `information_schema` (`is_generated=ALWAYS`) + `pg_indexes` (GIN).
  - **`search_chunks` is now hybrid** (Postgres branch): two owner+subject-scoped
    candidate arms — the existing pgvector cosine arm and a new lexical arm
    (`websearch_to_tsquery`/`ts_rank` over the GIN-indexed tsvector, config matching the
    column's `'simple'`) — fused by `rrf.py`'s `reciprocal_rank_fusion` (pure, DB-free:
    fuses on **rank position**, `score = Σ 1/(k+rank)`, `k=60`, since cosine distance and
    `ts_rank` are different scales and can't be added), bounded to `RERANK_CANDIDATE_POOL`,
    then the same `_rerank_candidates` (Cohere Rerank) final stage. The RRF score rides
    along so a rerank *failure* falls back to fused order.
  - **Every guarantee preserved**: both arms carry `owner_id + subject_id` (the FTS arm
    is a new tenant-leak surface — filter not optional); the SQLite branch still returns
    filtered-but-unranked (FTS/`<=>` are Postgres-only), so the offline scoping tests
    pass unchanged; graceful rerank fallback intact; Ask (stream + non-stream) unchanged
    — same `search_chunks` entry point, no ask-side edits.
  - Tests: `test_rrf.py` (9, offline, pure — order preserved, both-arms item outranks
    single-arm, agreed-top wins, one/both/no arms empty, deterministic tie-break,
    exact `1/(k+1)` score, k dampening). `test_search.py`: SQLite scoping unchanged +
    a live test asserting hybrid surfaces an exact keyword/code match (`ISO-9001`) as
    the top result through the real pipeline (the FTS arm's whole point). Backend
    **159 passed** (8 deselected live, up from 150/7), `ruff` clean.
  - **Live-verified** against real Neon + Cohere + Claude: the live search tests
    (hybrid returns the exact-keyword chunk first; on-topic still ranks first) and both
    live **Ask** tests (non-stream + streaming) — grounded, cited answers through the
    hybrid path end-to-end. Neon confirmed clean afterward.

- [x] Flashcards backend — SM-2 spaced-repetition scheduling + Claude tool-use
  generation + generate/list/due/review/delete. Phase 3 backend done; frontend next.
  - **`sm2.py`**: the canonical SuperMemo SM-2 algorithm as a **pure function** — no DB,
    no I/O, no `datetime.now()` inside (`now` is always caller-supplied, so every rule
    is deterministically testable). Grade < 3 resets `repetitions`/`interval_days`
    (relearn) but does **not** reset `ease_factor` — only the unconditional ease-update
    formula (applied on every review, pass or lapse) nudges it down. This is the classic
    SM-2 bug this codebase specifically guards against: conflating "reset progress" with
    "reset ease" would wipe out a card's entire easing history on one slip. Grade ≥ 3
    advances: rep 1 → 1 day, rep 2 → 6 days, rep *n* → `round(prev_interval *
    ease_factor)`. `ease_factor` floored at `1.3` (SuperMemo's documented minimum) so
    repeated low grades can't drive intervals negative/inverted.
  - **`models.py`**: `Flashcard` (`subject_id` FK, `owner_id`-scoped like `Quiz`, `front`,
    `back`, + SM-2 state: `repetitions`, `ease_factor`, `interval_days`, `due_at`,
    `last_reviewed_at`). Plain FK column, no ORM cascade. New cards default
    `due_at=now`/`repetitions=0`/`ease_factor=2.5`/`interval_days=0` — due immediately,
    so they appear in the very first due-cards review. Migration `b27704cd2174`, applied
    to Neon, confirmed via `information_schema`; `alembic check` reports no drift.
  - **`generation.py`**: mirrors `quiz/generation.py` exactly (DECISIONS.md #5) — a
    forced `record_flashcards` tool with a strict `input_schema` (`front`/`back`,
    `additionalProperties: false`), `tool_choice` forcing the call, defensive
    `_parse_flashcards` validation (an empty-string side is schema-valid but useless, so
    it's still rejected), `FlashcardGenerationError` on any malformed/empty/API failure.
    Missing `ANTHROPIC_API_KEY` → bare `RuntimeError`. Multilingual.
  - **`service.py`**: `generate_flashcards` verifies ownership → samples material (reuses
    `documents.service.sample_subject_chunk_texts`, no re-embedding) → generates →
    persists in one transaction (nothing on failure). `list_flashcards`/
    `list_due_flashcards` are subject-scoped; `review_flashcard`/`delete_flashcard`/
    `get_flashcard` are **owner-scoped by id alone** (same pattern as
    `documents.service.get_document_by_id`) since neither review nor delete carries
    `subject_id` in its URL. `review_flashcard` validates `grade` 0-5 before touching
    `sm2.review` (`InvalidGradeError`) — defense-in-depth; the HTTP schema
    (`ReviewRequest.grade: Field(ge=0, le=5)`) already rejects it at the boundary.
    `list_due_flashcards`/`review_flashcard` both accept an overridable `now` so no
    caller depends on wall-clock timing for correctness.
  - **`router.py`**: two routers, same split as `ask.router`'s
    `router`/`conversations_router` — `router` (subject-scoped: generate/list/`/due`),
    `flashcards_router` (flat, owner-scoped-by-id: review/delete). Thin
    exception→HTTP translation (404 unowned subject, 422 no material, 502 generation
    failure, 422 defensively for `InvalidGradeError`). Wired into `main.py` +
    `alembic/env.py`.
  - Tests: `test_sm2.py` (18, pure/deterministic — first/second/nth successful interval,
    any lapse grade 0-2 resets identically, a lapse decrements ease **without**
    resetting it, perfect grade increases ease, grade 4 is the formula's exact
    zero-crossing, repeated low grades floor at `1.3` both over many reviews and in a
    single review from near the floor, out-of-range grades raise, `due_at = now +
    interval`, `review()` doesn't mutate its input). `test_flashcard_generation.py` (9,
    Anthropic client mocked directly, same pattern as `test_quiz_generation.py`).
    `test_flashcards.py` (22 SQLite integration + 1 live): generated cards start with
    default SR state and are due immediately; 404/422/502 paths (and nothing persisted
    on a generation failure); `num_cards` passthrough + bounds (0/51 → 422); due-cards
    filtering (a manually future-dated card is excluded); review advances the schedule
    on a pass and resets `repetitions` on a lapse without losing all ease progress;
    out-of-range grade → 422; review/delete 404 for missing/another-owner and leave the
    card intact. Backend **208 passed** (9 deselected live, up from 159/8), `ruff`
    clean.
  - **Live-verified end-to-end** two ways: (1) the `-m live` flashcards test — real
    Neon + Cohere + Claude tool-use generates well-formed cards, a real review advances
    the schedule, cleanup removes **both** the Neon rows *and* the R2 object the
    uploaded document created (the existing quiz/search live tests leave that R2 object
    orphaned — confirmed via `list_objects_v2`, not repeated here). (2) The full real
    stack — real Inngest Dev Server + real R2/Neon/Cohere/Claude — real HTTP upload →
    `pending` → `ready` in ~5s → `POST /flashcards` → 4 well-formed cards, all due
    immediately → a real review via `POST /flashcards/{id}/review` correctly advanced
    `repetitions`/`interval_days`/`due_at` and the card correctly dropped out of
    `GET /due` afterward. Cleaned up via real `DELETE`s; Neon **and** R2 both confirmed
    clean afterward. Not click-tested in a real browser (no browser/Clerk auth here —
    the flashcards frontend is the next increment anyway).

- [x] Flashcards frontend — generate, an SM-2 review session, delete. Closes Phase 3.
  - `app/subjects/[subjectId]/flashcards/page.tsx`: generate form (`num_cards` 1-50,
    default 10) and the card list (front + muted back, delete). Generate guards
    double-submit and shows "Generating…" (live Claude call); 422/502 mapped via
    `friendlyFlashcardError` off the real `response.status` (hand-raised
    `HTTPException`s aren't in the typed error shape). Delete mirrors the
    delete-document/delete-quiz pattern exactly. A **"Review (N)"** button shows the
    live due count (its own `GET /due` query) and links to the review session,
    disabled at 0.
  - `app/subjects/[subjectId]/flashcards/review/page.tsx`: fetches `/due` **once** and
    steps through that fixed snapshot by index (`reviewProgress.ts`) — deliberately not
    re-deriving "current card" from a live `/due` query each render, since a background
    refetch dropping the just-graded card would reshuffle the session mid-review.
    Shows the front; "Show answer" reveals the back; four grade buttons — **Again=1,
    Hard=3, Good=4, Easy=5** (`gradeButtons.ts`, Anki-style, not six raw SM-2 numbers)
    — `POST` the review and advance. Again uses the `destructive` token; Easy uses the
    `--success` token (added in the quiz increment) via a `className` override on the
    `outline` variant (`twMerge`-safe). Empty/complete states: "No cards due right now"
    or "Done for now! You reviewed N cards."
  - Subject-detail page gains a "Flashcards" (outline) button beside Quizzes/Ask.
  - New pure helpers, all unit-tested: `lib/flashcardError.ts` (`friendlyFlashcardError`
    — 422/502/other, 3 tests), `lib/gradeButtons.ts` (`GRADE_BUTTONS` pins the exact
    label→grade mapping sent to `POST /flashcards/{id}/review`, `isLapseGrade` mirrors
    the backend's `sm2.PASSING_GRADE=3` boundary, 7 tests), `lib/reviewProgress.ts`
    (session position/remaining/completion from a fixed total + index, pure, 6 tests).
  - `schema.d.ts` regenerated (`FlashcardRead`/`FlashcardGenerateRequest`/
    `ReviewRequest` + the 4 routes now typed) — no hand-edits.
  - Verified: `tsc --noEmit` clean, `eslint` clean, **80 passed** (19 files, up from
    65/16), `npm run build` succeeds (both new routes compile:
    `/subjects/[subjectId]/flashcards` and `.../flashcards/review`).
  - **Live-verified**: no browser available in this environment (standing gap across
    every frontend page here), so this drove the **exact same real HTTP endpoints and
    payload shapes the pages call** through the full real stack (real Inngest Dev
    Server + real R2/Neon/Cohere/Claude) instead — upload → `ready` → generate 4 real
    cards → confirm all due immediately (matches the list page's `Review(4)` badge) →
    grade one card with each of the four buttons (Again/Hard/Good/Easy) → confirmed
    Again resets `repetitions` to 0 while Hard/Good/Easy all advance it to 1, every
    grade's `due_at` moved forward → confirmed all four graded cards correctly dropped
    out of a fresh `/due` fetch (0 remaining). Cleaned up via real `DELETE`s; Neon and
    R2 both confirmed clean afterward.

- [x] Progress tracking backend — read-only aggregation over existing data. First
  Phase 4 increment (Polar billing, the other half of Phase 4, is blocked — see
  "Blockers" below).
  - New `app/modules/progress/` — **no models of its own**, same shape as `ask`: every
    query reads `Document`/`Flashcard`/`Quiz` directly, filtered by `owner_id` alone
    (each already carries its own denormalized `owner_id` column, so "only this
    caller's data" needs no join through `Subject`). Efficient aggregates throughout —
    `COUNT`/`GROUP BY` via SQLAlchemy `func`, never "load every row and count in
    Python" (confirmed the exact `session.exec(select(func.count())...).one()` /
    grouped-row return shapes empirically before writing the real queries).
  - `service.py`: `_document_status_counts` (one `GROUP BY` for ready/pending/failed —
    natural fit for "counts by category" over three separate filtered `COUNT`s).
    `_flashcard_progress` (`due`/`new`/`learning`/`mature`) — `new` (never reviewed:
    `repetitions == 0 AND last_reviewed_at IS NULL`) and `mature`
    (`interval_days >= MATURE_INTERVAL_DAYS_THRESHOLD`) are mutually exclusive by
    construction (a card only gets a non-zero interval via a review, which always sets
    `last_reviewed_at`), so `learning = total - new - mature` needs no fourth query —
    and correctly counts a *lapsed* card (`repetitions` reset to 0 but
    `last_reviewed_at` still set) as `learning`, not `new` again. `due` is a separate,
    orthogonal `COUNT` (a card can be new-and-due, learning-and-due, or
    mature-and-due). `MATURE_INTERVAL_DAYS_THRESHOLD = 21`, documented — matches
    Anki's own young/mature cutoff, a familiar reference point rather than an arbitrary
    number. `_quiz_count`.
  - **Quiz count is quizzes *generated*, not a performance history** — a deliberate
    scope decision, documented in the code: quiz *attempts/scores* aren't persisted
    anywhere (grading is entirely client-side, see the quiz module's answer-key
    decision — nothing is ever submitted back to the server). Tracking quiz
    performance would need a new `QuizAttempt` model (`quiz_id` FK, `owner_id`,
    `score`, `total`, `created_at`) + a submission endpoint + its own migration/tests/
    tenant-scoping — **noted here as a follow-up, not built in this focused,
    read-only-over-existing-data increment.**
  - `get_subject_progress` calls `require_owned_subject` first — a progress endpoint
    that revealed *counts* for a subject the caller doesn't own would itself be a
    tenant leak, so ownership is checked before any aggregate runs (→
    `SubjectNotFoundError` → 404). `get_overall_progress` is owner-scoped only, summing
    across every subject the caller owns.
  - `router.py`: `GET /subjects/{subject_id}/progress` (per-subject) and `GET
    /progress` (overall) — same subject-scoped-router / flat-router split as
    `ask.router`. Wired into `main.py`.
  - Tests (`test_progress.py`, 10, offline/SQLite, **no mocking anywhere in the file**
    — no Claude/Cohere/R2/Inngest in this module at all, it's pure DB aggregation):
    a hand-computed 5-flashcard fixture exercises every SM-2 bucket at once (including
    the easy-to-get-wrong lapsed-card case above); a zeroed-out subject with no data; a
    sibling subject's data excluded from a per-subject rollup; 404 for missing/another-
    owner's subject; overall progress correctly summing across *all* the caller's
    subjects; a zeroed overall for a caller with none; **another owner's identical
    dataset never bleeding into `/progress`, checked from both directions** (the
    classic place a cross-tenant count leaks); and one direct service-level test
    pinning `get_subject_progress`'s overridable `now` (mirrors
    `flashcards_service.list_due_flashcards`'s same deterministic-clock pattern — the
    HTTP-level tests instead use wall-clock-relative fixture dates, since the router
    has no client-suppliable `now`). Backend **218 passed** (9 deselected live, up from
    208/9 — no new live test needed: no Postgres-specific aggregate here), `ruff`
    clean.
  - **Live-verified against real Neon data** (the user's own real Clerk-authenticated
    subjects/documents/flashcards/quizzes from earlier browser testing, not seeded by
    this verification) — hand-computed the true aggregates via direct SQL first (1
    ready document, 10 new/due flashcards, 2 quizzes on one real subject; all-zero on a
    second real subject with no material uploaded yet), then confirmed
    `GET /subjects/{id}/progress` and `GET /progress` return **exactly** those numbers
    for both subjects individually and summed overall, plus a 404 for an unowned
    subject id. Read-only the whole way — nothing created, modified, or deleted.
    (Caught one non-issue along the way: an initial SQL check briefly returned stale
    counts immediately after connecting — a Neon serverless cold-start read-consistency
    blip, not a bug; re-querying fresh resolved it before any assertion was written
    against it.)

- [x] Progress dashboard frontend — per-subject progress page + an overall `/dashboard`.
  Closes Phase 4's Progress half (Polar billing, the other half, is still blocked).
  - `components/progress-stats.tsx`: the shared rendering piece both new pages use —
    three headline stat tiles (documents/flashcards/quizzes), a document-status badge
    row, and a flashcard mastery breakdown. **Loaded the `dataviz` skill before writing
    this** (it's a data visualization, per the skill's own trigger). The mastery
    breakdown is a **status-encoded** segmented bar reusing the app's existing semantic
    tokens — `muted-foreground` for new/not-started, `primary` for learning/in-progress,
    `success` for mature/well-learned — rather than inventing a new categorical palette;
    a design-system's pre-existing status tokens are exactly the kind of parameter the
    skill's method expects to be handed, not re-derived. Every segment is still paired
    with a visible label + count in the legend beneath the bar (never color alone, one
    of the skill's non-negotiables). The bar itself never re-buckets a single card —
    `lib/flashcardMastery.ts`'s `masteryRows`/`percentMature` only format the
    already-partitioned `new`/`learning`/`mature` counts the API returns, so the UI
    can't silently disagree with the backend's bucket math. `lib/documentProgress.ts`
    does the equivalent for `DocumentStatusCounts`, reusing the same
    ready/pending/failed → badge-variant mapping as the existing `documentStatus.ts`.
  - `app/subjects/[subjectId]/progress/page.tsx`: fetches `GET
    /subjects/{subject_id}/progress`. Same states as every other subject-scoped page —
    "Subject not found" (checked via `subjectQuery.isError`, same as the quiz/flashcards
    pages, not just a generic progress-load error), loading, and — the empty-account
    case the task called out specifically — a friendly "Nothing to show yet" nudge
    linking back to the subject, instead of a zeroed-out stat grid with no context, when
    the subject genuinely has no documents/flashcards/quizzes.
  - `app/dashboard/page.tsx`: fetches `GET /progress` (overall, across every subject the
    caller owns). `subject_count === 0` renders a "Welcome to StudyMate / get started"
    card instead of an all-zeros dashboard. **Added `/dashboard` to the Clerk middleware
    matcher** (was `/subjects(.*)` only) — without this the page renders but its API
    calls 401, since nothing protects it or forces a session. Linked from the Subjects
    page header (beside `UserButton`) and from the home page for a signed-in visitor.
  - **Clerk API surface changed since this app was scaffolded**: `SignedIn`/`SignedOut`
    aren't exported by the installed `@clerk/nextjs` (`7.5.18`) — confirmed by reading
    the package's own `.d.mts` type declarations rather than assuming, since `tsc`
    caught the wrong import immediately. This version replaced them with a single
    `<Show when="signed-in" fallback={...}>` component (`when` also accepts
    `"signed-out"`, authorization descriptors, or a predicate) — used that instead.
  - Subject-detail page gains a "Progress" (outline) button alongside
    Flashcards/Quizzes/Ask.
  - New pure helpers, unit-tested: `lib/flashcardMastery.ts` (`masteryRows` — 4 tests,
    `percentMature` — 3 tests) and `lib/documentProgress.ts` (`documentStatusRows` — 3
    tests), 10 tests total, covering the empty-deck / zero-count cases (`0`, never
    `NaN`/`Infinity`).
  - `schema.d.ts` regenerated (`SubjectProgress`/`OverallProgress`/
    `DocumentStatusCounts`/`FlashcardProgress` + the 2 routes now typed) — no
    hand-edits.
  - Verified: `tsc --noEmit` clean, `eslint` clean, **90 passed** (21 files, up from
    80/19), `npm run build` succeeds (both new routes compile: `/dashboard` and
    `/subjects/[subjectId]/progress`; `/` itself moved from a static to a dynamic route
    once it needed `<Show>`'s auth-aware rendering — expected, not a regression).
  - **Live-verified**: no browser available in this environment (the standing gap noted
    on every frontend page in this project), so this drove the **exact real HTTP
    endpoints and payload shapes both pages call** against real Neon data (the same real
    subjects/documents/flashcards/quizzes used to live-verify the backend) — confirmed
    both `SubjectProgress` and `OverallProgress` return the exact shape
    `ProgressStats`/`masteryRows`/`documentStatusRows` expect, and that
    `new + learning + mature == total` holds against the real payload (the exact
    partition invariant the stacked-bar rendering depends on). Read-only.

- [x] Plan tiers + usage-limit enforcement — the **entitlement layer** Polar will plug
  into. Provider-agnostic on purpose: no Polar SDK, no secrets, no plan-change endpoint.
  Polar itself stays blocked on keys; this half of billing doesn't depend on it.
  - New `app/modules/billing/` (router + service + schemas + models).
  - **`models.py`**: `UserPlan` (`owner_id` PRIMARY KEY, `plan` enum
    free/pro/business, `updated_at`) — one row per owner, and **absence of a row means
    Free**, never an error (a brand-new user with no billing row uses the app up to the
    Free cap). This is the exact row a future Polar webhook upserts on
    subscribe/cancel; nothing else changes when it arrives. `owner_id` being the PK
    makes it inherently tenant-scoped.
  - **`GenerationUsage`** (`owner_id`, `day`, `kind`, `count`, unique on the triple):
    counts generation **events** per owner per UTC day. **Why a table instead of
    counting existing rows by `created_at`** — the decision the task asked to document:
    rows don't map to events 1:1. One `generate_quiz` writes one `Quiz` row (countable),
    but one `generate_flashcards` writes *N* `Flashcard` rows — counting those would
    charge a single 10-card generation as 10 against the daily cap. Bounded growth
    (≤2 rows/owner/day), and it stays correct if either module's rows-per-generation
    ratio ever changes.
  - **`service.py` owns all quota counting** — the other four modules each gained
    exactly one guard call and zero counting logic. One documented `LIMITS` dict holds
    every cap in the product (Free 3 subjects / 10 docs per subject / 20 generations per
    day; Pro 50 / 200 / 200; Business unlimited via `None`, which short-circuits the
    count query entirely), so tuning a tier is a one-line change. **The user should
    confirm/adjust these numbers** — they're the task's defaults.
  - **Tenant scoping is the security crux here**: a usage count that read across owners
    would let one user's activity consume — or bypass — another's quota. Every count
    filters `owner_id` directly (each table carries its own denormalized `owner_id`, so
    no join can go wrong); the per-subject document count filters `owner_id` **and**
    `subject_id`, since either alone is wrong in a different way. Asserted per-cap in
    the tests.
  - **Ordering contract, decided and documented in code**: `ensure_can_*` runs at the
    START of each create path — before the R2 upload, before the Claude call, before any
    row is written — so a rejected request does no billable work and persists nothing.
    `record_generation` **stages the increment without committing**, so the caller's
    existing `session.commit()` persists the counter and the generated rows in the *same
    transaction* (neither can land without the other), and it only runs *after*
    generation succeeded — a failed Claude call doesn't burn the user's daily quota.
    The check/increment race at the exact cap boundary is documented as an accepted ±1
    overshoot on a soft cost-bounding cap, rather than paying for `SELECT ... FOR UPDATE`
    lock contention.
  - **Days are UTC** (`_utc_day`) with an injectable `now` on every affected function —
    a local-time boundary would depend on server timezone and be untestable.
  - `PlanLimitExceededError` → **402 Payment Required** via an **app-wide exception
    handler** in `main.py`, not an identical `except` block in four routers: the mapping
    is the same everywhere, so one handler keeps those routers thin and any future
    guarded path gets it free (per-router try/except remains the pattern for
    *module-specific* exceptions, which genuinely differ). The body names the limit and
    cap in prose *and* carries `limit`/`plan`/`cap` as fields, so a client can act on it
    without parsing text.
  - `GET /billing/plan` → plan + limits + usage (`subjects`, `generations_today`), so a
    frontend can show "2 of 3 subjects used". **No plan-change endpoint on purpose** —
    that's the payment provider's job; a self-serve "set my own plan" route would be an
    entitlement bypass. Noted for when Polar lands.
  - Migration `48c8dee79a2c`, applied to Neon; enum labels confirmed lowercase via
    `pg_enum` (the `values_callable` fix), unique constraint + indexes verified,
    `alembic check` clean. Its `downgrade()` also DROPs the enum types — autogenerate
    omits that, and without it a downgrade leaves them behind and the next upgrade fails
    with "type already exists" (the pre-existing `documentstatus` migration has this
    gap; deliberately not repeated).
  - Tests: `test_billing.py` (26, offline/SQLite, no mocking — this module touches no
    Claude/Cohere/R2/Inngest): every cap asserted **exactly at its boundary** (Nth
    allowed, N+1th raises with the right limit/plan/cap); default-Free-when-no-row; Pro
    lifting a cap and Business unlimited; the document cap being per-subject not
    per-account; the generation cap counting quiz + flashcards **together** (combined
    cap); `record_generation` creating-then-incrementing one row per slot; its
    no-commit contract asserted by rolling the caller's transaction back and confirming
    the counter rolled back too; the UTC-day reset pinned with an injected `now`
    (exhausted at 23:59, fresh one second past midnight) and asserted day-bucketed
    rather than a rolling 24h window; **tenant isolation per cap**; and over-HTTP: a 402
    with the right fields, a rejected create persisting nothing, and inserting a Pro row
    (what Polar's webhook will do) lifting the cap immediately. Backend **244 passed**
    (9 deselected live, up from 218/9), `ruff` clean. **The 218 pre-existing tests
    needed no changes** — none of them exceeded a Free cap.
  - **Live-verified against real Neon** with a throwaway owner id (the real account's
    data untouched, confirmed): a no-row owner defaulted to Free with cap 3 → created 3
    subjects (all 201) → `GET /billing/plan` reported `subjects: 3` → the 4th returned
    **402** with `{"limit":"subjects","plan":"free","cap":3}` and "Upgrade your plan to
    continue" → confirmed the rejected create persisted nothing (still exactly 3) →
    inserted a Pro `UserPlan` row (simulating the future Polar webhook) → the same
    request that just 402'd returned **201**. All rows cleaned up afterward.

- [x] **Polar payment wiring — the last blocked Phase 4 item, now unblocked and done**
  (SANDBOX). Checkout + webhook → `UserPlan`. The entitlement layer was **not**
  redesigned: `LIMITS`, `ensure_can_*`, `record_generation`, the 402 handler are all
  untouched, and there is still no plan-change endpoint. `polar-sdk>=0.31` added.
  - **Step 0 caught a design-breaking mismatch before any code was written.** The three
    sandbox products (FREE $0 / PRO $20 / Business $100) were all **one-time purchases**
    (`recurring_interval: None`), not subscriptions. One-time products never emit
    `subscription.*` events — they emit `order.paid` — so the specced webhook would have
    been a fully-tested, green, *silently dead* integration: checkout works, plans never
    change. Nothing ever cancels or expires either, so $100 would have bought permanent
    unlimited Business. Escalated rather than guessed; the user chose recurring monthly.
    **Two new recurring monthly products created via the API** (Pro `5d19dae1…` $20/mo,
    Business `653e839c…` $100/mo), preserving the original price points. The three
    original one-time products were left untouched for the user to clean up.
  - **LIMITS vs the dashboard: no conflict** (the comparison the task asked for). The
    products carry no caps anywhere — empty descriptions, no metadata, no benefits — so
    nothing in Polar contradicts `LIMITS`, which remains the only thing enforcing
    anything. Names map cleanly onto the existing `Plan` enum.
  - `app/core/polar_client.py`: one shared client, `sandbox`/`production` via
    `POLAR_SERVER` (**defaults to sandbox** so a misconfigured deploy can't charge a real
    card). Missing creds → `PolarConfigError` at point of use naming the exact env var —
    same loud-failure pattern as r2/inngest/embedding. Secrets never logged, returned, or
    put in an exception message (asserted by a test). Deliberately Polar-only: it knows
    nothing about `Plan`/`UserPlan`, so `app/core` still never imports `app/modules`.
  - **Product → plan by id, not name** (`POLAR_PRODUCT_ID_PRO`/`_BUSINESS`): ids are
    stable, names are mutable labels — and this org's own products were already named
    inconsistently ("FREE"/"PRO"/"Business"), which is exactly how name-matching breaks.
    Mapping by name would also cost an API call per webhook. **No Free product id**: Free
    is the *absence* of a paid plan, so it's never sold (checkout 400s on it).
  - **Owner linkage is the crux.** The webhook has no Clerk JWT, so `create_checkout`
    plants the Clerk `owner_id` as `external_customer_id` while the caller *is*
    authenticated; the webhook reads it back from
    `subscription.customer.external_id` — only out of a signature-verified payload, never
    from a client-controllable field. A caller can't buy a plan for anyone else (tested:
    an `owner_id` in the request body is ignored in favour of the token's).
  - **Signature verification before anything else touches the payload or DB.** Raw
    `await request.body()` (re-serializing parsed JSON changes the bytes and breaks
    verification); the SDK's `validate_event` delegates to Standard Webhooks —
    constant-time compare + a timestamp freshness window, so replay protection is free and
    no crypto is hand-rolled. Bad signature → 403, nothing written. **A missing secret
    raises (500), never "unset → accept"** — an unverified webhook is a free-Business
    bypass.
  - **`revoked` downgrades, `canceled` does NOT** — the increment's subtlest decision,
    taken from the SDK's own docstrings rather than assumption: `canceled` is "cancellation
    scheduled, customer *may still have access until the end of the current period*",
    while `revoked` is "loses access immediately". Downgrading on `canceled` would cut off
    a customer who already paid through period end. `past_due` likewise waits (payment may
    recover; `revoked` fires if it doesn't). `subscription.updated` **is** handled, so a
    mid-period Pro→Business switch — which fires no `active` event — isn't silently missed.
  - **Downgrade sets `Plan.FREE` rather than deleting the row**, despite "no row" also
    meaning Free: deleting would discard `updated_at`, the ordering guard, so a stale
    `active` redelivered afterwards would find no row, look fresh, and silently re-grant a
    paid plan for free. **`updated_at` stores the *event's* timestamp, not wall-clock** —
    with processing time, a legitimately newer event that merely arrived a moment later
    would look older than the row and be dropped. `_as_utc` normalizes both sides: Polar's
    timestamps are aware, but `updated_at` round-trips through a `TIMESTAMP WITHOUT TIME
    ZONE` column and returns **naive**, which would otherwise `TypeError` on comparison.
  - Unknown product / missing `external_id` / unhandled event type → **200 `ignored`**,
    logged, nothing written: they're not errors (a non-2xx would make Polar retry forever
    an event that can never succeed), but they're never silently swallowed either.
    Checkout failures surface as real statuses (400 unpurchasable / 500 misconfig / 502
    upstream), never a 200 with no URL.
  - Tests: `test_polar.py` (37, network-free — the *client* is mocked, but **signatures
    are not**: payloads are signed with real HMAC via the same Standard Webhooks library
    the verifier uses and posted as real bytes at the real endpoint, since a stubbed
    signature check would prove nothing). Covers the checkout call shape + owner linkage;
    valid signature upserting; invalid signature, unsigned request, and a body **tampered
    after signing** all rejected with nothing written; missing secret failing loudly;
    subscribe lifting the subject cap over real HTTP and revoke reinstating it;
    canceled/past_due not downgrading; a tier switch; duplicate and **both** out-of-order
    directions; tenant isolation. Backend **281 passed** (10 deselected live, up from
    244/9), `ruff` clean. **The 244 pre-existing tests needed no changes.**
  - **Live-verified, in two halves — and the second half is only partly live:**
    1. **Checkout: genuinely live.** A real sandbox checkout created via the real API with
       a throwaway owner id, then read back from Polar to confirm `external_customer_id`
       persisted upstream. (Found along the way: `checkouts.list(external_customer_id=…)`
       can't find an *unpaid* checkout — that filter resolves through the customer
       relation, and `customer_id` is `None` until payment — so the test matches on the
       returned URL instead. The URL's last segment is a client secret, not the id.)
    2. **Webhook: NOT verified against real Polar delivery.** No `polar listen` tunnel was
       available (no Polar CLI in this environment), so **Polar has never actually
       delivered an event to this endpoint.** What *was* verified: the real app under
       uvicorn on a real socket against real Neon, driven with payloads signed by the
       **real** `POLAR_WEBHOOK_SECRET` from `.env` — valid → 200 `applied` + `pro` in Neon;
       **bad signature → 403 with the plan unchanged**; duplicate → `ignored_stale`;
       canceled → `ignored`, still `pro`; updated → `business`; stale → `ignored_stale`;
       revoked → `free`. Throwaway owner id; Neon confirmed at 0 `UserPlan` rows before
       and after. That proves the transport, the signature check and the DB write — it
       does **not** prove Polar's real delivery format or that the configured secret
       matches how events will actually be delivered. See "Blockers".

- [x] **Billing frontend — usage meters + upgrade prompts** (Phase 4). Consumes the two
  existing billing endpoints; **no backend change**. `schema.d.ts` regenerated so
  `PlanRead`/`Plan`/`CheckoutCreate*` are typed (offline via `app.openapi()` →
  `openapi-typescript`, identical to the live-server script).
  - **`/billing` page** (route added to `middleware.ts` protection): current plan + usage
    meters + upgrade options (only tiers above the current one). Upgrade button →
    `POST /billing/checkout` with a `success_url` of `${origin}/billing?upgraded=1` →
    redirect to Polar's hosted `checkout_url`. On return, `?upgraded=1` shows a
    plan-activating note and refetches the plan (webhook lands the change async). Reads the
    flag from `window.location.search` in an effect, not `useSearchParams` (no Suspense
    boundary needed).
  - **402 upgrade prompt**: subject-create now surfaces the plan-limit 402 as
    `<UpgradePrompt>` (backend's own limit/cap message + Upgrade→`/billing`) instead of a
    generic error. Reusable `UpgradePrompt` + `parsePlanLimitError` make the doc-upload /
    quiz / flashcard 402 paths a one-liner later (not yet wired).
  - **Pure helpers, tested**: `planLimits.ts` (`meterPercent` rounded/clamped, 0 for
    unlimited/zero-cap never NaN; `usageMeters` — subjects + daily-generations, `atLimit`
    at the exact cap, unlimited path) and `planLimitError.ts` (`parsePlanLimitError` —
    validates the untyped 402 body, null for non-402/malformed, message fallback).
    `max_documents_per_subject` intentionally not metered (per-subject cap, no account-wide
    number) — stated as a rule on the page. `UsageMeters` bars are `role="img"` with the
    used/cap text in the aria-label (never colour alone), `destructive` at the cap.
  - Frontend **106 passed** (25 files, up from 90/21), `tsc`/`eslint` clean, `npm run build`
    succeeds (`/billing` static). **Not browser-verified** (no browser here) — the
    checkout redirect + `?upgraded` refetch want a manual pass with real Clerk auth.

## Next (Phase 4+)
- **Confirm the Polar webhook against real delivery** — the one gap in the payment path;
  see "Blockers". Everything else in the payment path is live-verified.
- **Browser pass on the billing frontend** — the `/billing` page, the checkout→Polar
  redirect, and the `?upgraded=1` return-and-refetch all still want a manual click-through
  with real Clerk auth (no browser in this environment). Also fold the reusable
  `UpgradePrompt`/`parsePlanLimitError` into the document-upload / quiz / flashcard 402
  paths (currently wired only into subject-create).
- Remaining per `docs/plan.md`: multilingual polish, Business/Teams B2B (Phase 5).
- Still owed from earlier: a real-browser click-through of the async upload/poll/delete,
  quiz, hybrid-Ask, flashcards, and progress-dashboard flows with live Clerk auth (noted
  across several increments, never yet done — no browser available in this environment).

## Blockers / needs from user
- **Verify the webhook against real Polar delivery** — the only open item on billing.
  Polar has never actually delivered an event to `/billing/webhook`; everything else in
  the flow is live-verified (see the Polar increment above). Needs, from the user:
  1. `polar listen http://localhost:8000/billing/webhook` (Polar's own CLI tunnel — not
     installed in this environment), then a real sandbox checkout paid with a test card.
  2. **Confirm which webhook secret is in play**: `polar listen` prints its own secret,
     which may DIFFER from the dashboard endpoint's. `POLAR_WEBHOOK_SECRET` in `.env`
     must match whichever is actually delivering, or every event 403s.
  A dashboard webhook endpoint pointing at a public URL would work equally well.
- **Clean up the old one-time Polar products** (FREE $0 / PRO $20 / Business $100, all
  `recurring_interval: None`). They're superseded by the new recurring monthly Pro/Business
  and were deliberately left untouched. They are not wired to anything, so they're inert —
  but a one-time product can never drive a subscription, so nothing should point at them.
- **Confirm/adjust the plan limits** in `billing/service.LIMITS` — still the task's
  defaults (Free 3 subjects / 10 docs per subject / 20 generations per day; Pro
  50/200/200; Business unlimited). One dict, one-line changes. Note the sandbox products
  state no caps at all, so `LIMITS` is the *only* thing enforcing them — nothing
  contradicts it, but nothing corroborates it either.
- **Polar is SANDBOX-only so far.** Going live needs `POLAR_SERVER=production`, a
  production org token, production product ids, and a production webhook secret —
  production has its own separate dashboard, products and tokens.
- Neon, Clerk, Cohere, Anthropic, Inngest, R2, and Polar (sandbox) keys are all in
  `backend/.env`.
