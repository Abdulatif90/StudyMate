# Worklog

Log of completed work (newest first). Each entry: what was done, tests, commit.

## 2026-07-16 — CORS + first frontend increment (Next.js, Clerk, Subjects page)
- **CORS** (`79d4359`): `CORSMiddleware` in `app/main.py`, origins from the new
  `Settings.cors_origins` (comma-separated string, `cors_origin_list` property
  splits it — chosen over pydantic-settings' native list-typed fields, which expect
  JSON in `.env`, more friction than this needs). Defaults to
  `http://localhost:3000`. `.env.example` documents the override.
  `tests/test_cors.py` (3): the comma-split itself, an allowed origin gets
  `access-control-allow-origin` back, a disallowed one doesn't.
- **Frontend scaffold** (`75c58f9`): Next.js 15 (App Router + TS + Tailwind) in
  `frontend/`. `@clerk/nextjs` (`ClerkProvider` + `clerkMiddleware` protecting
  `/subjects(.*)`, sign-in/sign-up pages), `@tanstack/react-query`, typed API client
  (`openapi-typescript` generates `schema.d.ts` from the backend's live
  `/openapi.json`, wrapped by `openapi-fetch`), shadcn/ui (Base UI variant:
  button/card/input/label). `useApiClient()` hook attaches the caller's Clerk
  session token as `Authorization: Bearer` via an `openapi-fetch` request
  middleware, registered once per mount through a ref so a token refresh doesn't
  need re-registration. First protected page, `/subjects`: list + create, wired to
  the typed client + React Query.
  - This work had actually already been done in a prior session but was never
    committed or logged — found on resuming (`frontend/` was untracked, fully
    built, with no mention in this file or PROGRESS.md). Verified it thoroughly
    before trusting it: `tsc --noEmit` clean, `eslint` clean, backend suite still
    70 passed (67 existing + 3 new CORS tests) with `ruff check` clean, then started
    both `uvicorn` and `npm run dev` and drove the real flow.
  - **Real bug caught during that live check, fixed before committing**: Base UI's
    `Button` primitive (the shadcn variant this project uses, not Radix) defaults to
    `nativeButton={true}` and throws a console error when the rendered root isn't an
    actual `<button>` — triggered by the homepage's two CTA buttons, which render as
    `next/link` via Base UI's `render` prop. Fixed by adding `nativeButton={false}`
    alongside `render` on both.
  - **`frontend/.gitignore` bug caught before committing**: its `.env*` line (meant
    to keep real secrets out of git) also matched `.env.local.example`, the
    committed template file — same role as `backend/.env.example`, which the root
    `.gitignore`'s narrower `.env`/`.env.local`/`.env.*.local` patterns don't touch.
    `git check-ignore -v` confirmed the exact matching line before fixing. Added
    `!.env*.example` so the template stays tracked; confirmed with `git status`
    that no real `frontend/.env` (which holds the actual Clerk keys) was ever staged.
  - **Live-verified the full stack together, for the first time on this project**:
    the user signed in through the real Clerk UI, created a subject via the
    `/subjects` page, and confirmed both that FastAPI's JWKS-based
    `get_current_user_id` accepted the real Clerk-issued JWT and that the subject
    row landed in Neon — the first end-to-end confirmation that the frontend's
    Clerk app (publishable/secret keys) and the backend's
    (`CLERK_JWKS_URL`/`CLERK_ISSUER`) are genuinely the same Clerk instance, not
    just independently configured to look right.
  - Split into two commits on `develop` (CORS first, since the frontend depends on
    it working; frontend second) per the task's instructions, both pushed.
- Full backend suite: **70 passed, 2 deselected** (3 new CORS tests); `ruff check`
  → clean. Frontend: `tsc --noEmit` clean, `eslint` clean.

## 2026-07-15 — Conversations: multi-turn chat history for Ask
- `app/modules/ask/models.py` (new): `Conversation` (`subject_id` FK — a conversation
  belongs to exactly one subject, `owner_id`, `title?`, `created_at`) and
  `ConversationTurn` (`conversation_id` FK, `owner_id`, `question`, `answer`,
  `sources` as JSON, `created_at`). `sources` stores exactly what was shown to the
  user at the time (filename, chunk index, text, similarity score) rather than
  re-deriving it later — the chunks a turn cited could be re-embedded or deleted
  afterward, and the transcript should stay accurate to what was actually said.
- `documents/service.py`: renamed `_require_owned_subject` → public
  `require_owned_subject` (dropped the leading underscore) so `ask/service.py` could
  reuse the exact same ownership check before creating or loading a conversation,
  instead of duplicating the one-line None-check across modules.
- `AskRequest` gains optional `conversation_id`; `AskResponse` gains `conversation_id`
  (always present in the response — a new conversation is created whenever none is
  given, so single-shot callers who never pass it keep working unchanged, just with a
  conversation silently created behind the scenes for them).
- `service.ask_question` rewired: verify subject ownership first, then either load
  the given conversation or create a new one. Loading checks **both** that the
  conversation is owned by the caller **and** that it belongs to the subject in the
  URL — a conversation_id from a different subject 404s rather than silently mixing
  context across subjects. Loads the conversation's full history via `list_turns`,
  then caps it to the most recent `MAX_CONTEXT_TURNS` (10) for what actually gets
  sent to Claude — `list_turns` itself (used by `GET /conversations/{id}`) still
  returns the complete transcript for display. **Always saves a turn**, including
  both graceful-degradation paths (no relevant material, Claude failure) — the
  transcript should show what was actually asked and answered regardless of outcome,
  matching the task's explicit "always save the new turn" instruction literally.
- `llm.ask_claude` gains `prior_turns: list[dict] | None`: built as genuine prior
  turns in Claude's native multi-turn `messages` list (alternating `user`/
  `assistant` entries), not text stuffed into the system prompt — this is the
  idiomatic way to give the Messages API conversation continuity. Only the
  *current* question's message carries retrieved excerpts; earlier turns carry just
  their original question and answer, so a follow-up like "can you give an example?"
  can be resolved using conversation context without re-supplying old source
  material verbatim.
- New endpoints, two `APIRouter`s in `ask/router.py` now (different path prefixes —
  one router can't serve both `/subjects/{id}/ask` and `/conversations`): `GET
  /conversations` (owner-scoped list, newest first), `GET /conversations/{id}` (with
  the full turn history), `DELETE /conversations/{id}` (optional per the task,
  included for CRUD completeness matching subjects/documents). Both wired into
  `app/main.py`.
- Migration `ee395363541a_add_conversations_and_conversation_turns_tables`. Caught
  before applying (not after): autogenerate rendered `ConversationTurn.sources` as
  nullable, but it should never actually be `NULL` — the Python-side default is
  `default_factory=list` (an empty list, never `None`), so a nullable DB column was
  looser than what the application actually guarantees. Tightened to
  `Column(JSON, nullable=False)` in the model, deleted the not-yet-applied migration,
  regenerated it, and confirmed `sources` came out `NOT NULL` this time before
  applying to Neon.
- **Real bug, caught by the live end-to-end test — in production service code this
  time, not a one-off test cleanup script**: `service.delete_conversation` deleted
  every `ConversationTurn` first, then the `Conversation`, in that order — and still
  hit a `ForeignKeyViolation` on the conversation delete. Same root cause as the
  Document/DocumentChunk cleanup surprise from the chunking increment: there's no
  ORM-level `relationship()`/cascade between these models (consistent with this
  codebase's plain-FK-column style everywhere), so SQLAlchemy's flush doesn't know
  the two deletes are order-dependent — calling `session.delete()` in the "right"
  order is not sufficient on its own to guarantee the "right" order of DELETE
  statements at flush time. Fixed with an explicit `session.flush()` between the
  turn deletes and the conversation delete, forcing the child rows to actually be
  removed from the DB before the parent delete is even attempted. This is worth
  remembering as a general rule for this codebase specifically: **any function that
  deletes a parent row with FK-referencing children, without an ORM relationship
  defined, needs an explicit `session.flush()` between the child deletes and the
  parent delete** — this is the second time this exact shape of bug has appeared,
  and the fix pattern is now established. Verified by re-running the live test after
  the fix, not just reasoning about it — it failed clearly before, passed cleanly
  after.
- Tests:
  - `tests/test_ask.py` (+10 default): a follow-up question reuses the same
    conversation, and the *exact* prior question/answer pair is asserted in the
    `prior_turns` kwarg actually passed to the (mocked) `ask_claude` call — not just
    that conversation_id matched, but that the right context was actually
    constructed and forwarded; a conversation_id from a different subject 404s;
    turns are saved even when there's no relevant material or Claude fails, verified
    by re-fetching the conversation afterward and checking its saved transcript (not
    just the immediate HTTP response); `GET`/`DELETE /conversations` are
    owner-scoped (another owner gets 404 / an empty list, matching the pattern used
    everywhere else in this codebase).
  - Live test extended (same `@pytest.mark.live` + `DATABASE_URL` `skipif` as
    before) with a genuine second turn in the same conversation against real
    Claude — confirms `conversation_id` stays stable across both calls and both
    turns actually persist — then uses `delete_conversation` itself for cleanup,
    which is exactly what surfaced the FK-ordering bug above (a good reminder that
    exercising real cleanup code paths in live tests, not just ad hoc scripts, is
    what caught this).
- Full suite: plain `pytest` → **67 passed, 2 deselected** (fast, offline);
  `pytest -m live` → **2 passed** (this one extended + retrieval's), confirmed Neon
  left clean (0 rows across all five tables) afterward. `ruff check` → clean.

## 2026-07-15 — Ask endpoint: RAG, non-streaming (Claude + search_chunks)
- User added `ANTHROPIC_API_KEY` to `backend/.env`. `requirements.txt`: added
  `anthropic`. `Settings.anthropic_api_key`; `.env.example` uncommented.
- Before writing any code, installed `anthropic` (0.116.0) and introspected it
  directly — same discipline as `cohere`/`pgvector` earlier this project. Confirmed:
  `Anthropic(api_key=...)`, `.messages.create(model=, max_tokens=, system=,
  messages=[...])`, response shape `Message.content` → list of `TextBlock` (`.text`),
  and the common exception base is `anthropic.AnthropicError` (this SDK does have one,
  unlike Cohere's — still catch bare `Exception` in `ask_claude` for consistency with
  `embedding.py`/`parsing.py`'s established pattern, since network-layer failures
  might not reach even a well-designed SDK exception hierarchy).
- New domain module `app/modules/ask/` — per CLAUDE.md's structure, already named as a
  planned module (`subjects, documents, ask, quiz, flashcards, progress, billing`).
  No `models.py`: Ask doesn't persist anything of its own, it only orchestrates
  subjects/documents services plus Claude.
  - `llm.py`: `ask_claude(question, chunks) -> str` via `claude-haiku-4-5-20251001`.
    System prompt requires: answer only from the given excerpts (never outside
    knowledge), cite every claim as `(filename, chunk N)`, refuse plainly when the
    excerpts don't cover the question, match the question's language regardless of
    what language the excerpts are in. Missing `ANTHROPIC_API_KEY` → bare
    `RuntimeError` at point of use (deploy mistake, same as `db.py`/`auth.py`/
    `embedding.py`); any Claude API/network failure → `LLMError` (a per-request
    problem, handled gracefully by the caller).
  - **Live-verified `ask_claude` against the real Anthropic API before writing a
    single test**: confirmed the exact citation format `(filename, chunk N)` shows up
    in real output; confirmed it refuses a question the excerpts don't cover instead
    of answering from outside knowledge ("I can't answer that question based on the
    excerpts provided..."); confirmed it responds in Spanish to a Spanish question
    even though the source excerpt was in English.
  - `documents/service.py`: added `get_documents_by_ids(session, owner_id,
    document_ids) -> dict[uuid.UUID, Document]` — one batched query instead of one
    per document, for looking up filenames to cite as sources.
  - `service.ask_question(session, owner_id, subject_id, question) -> AskResponse`:
    `search_chunks` (built in the retrieval increment) → `get_documents_by_ids` for
    filenames → `ask_claude`. **All graceful degradation lives here, not the
    router**: an empty retrieval result and a Claude `LLMError` both return a normal
    200 `AskResponse` with an explanatory `answer` and empty `sources` — deliberately
    not HTTP errors, so a frontend never needs a special-case branch for "the AI
    couldn't answer" vs. "something actually broke". The only exception that reaches
    the router is `SubjectNotFoundError` (raised inside `search_chunks` itself),
    translated to 404 there.
  - `router.py`: `POST /subjects/{subject_id}/ask`, thin — just the 404 translation.
    Wired into `app/main.py`.
- Tests:
  - `tests/test_llm.py` (3): mocks the Anthropic client itself (not our wrapper) —
    call shape (model, system prompt, excerpt formatting, question) matches exactly
    what's sent; Claude/network failures wrapped as `LLMError`; missing key raises
    `RuntimeError`.
  - `tests/test_ask.py` (5 default + 1 live): answer+sources returned correctly, with
    an assertion that the *actual* retrieved chunk content was what got passed to the
    (mocked) Claude call — not just that some answer came back; 404 for a subject
    that doesn't exist and for another owner's subject (the same tenant-scoping
    pattern as every other endpoint); no-documents-yet returns the graceful
    "couldn't find" message with zero sources and never even calls Claude
    (`assert_not_called()` — confirms the short-circuit, not just the message text);
    a forced `LLMError` still returns 200 with the graceful "try again" message.
    On SQLite, `search_chunks` never calls Cohere at all for the query side (already
    true from the retrieval increment — the `<=>` branch is Postgres-only), so these
    tests only needed to mock document-upload's `embed_texts`, not anything
    query-related — the ask flow itself only needed Claude mocked.
  - Live test (`@pytest.mark.live`, plus the existing `DATABASE_URL` `skipif` as a
    second guard): runs the real pipeline end-to-end — real Neon storage, real Cohere
    embeddings on both the document and query side, real Claude generation — and
    asserts the answer is actually grounded in the material (not a refusal) with the
    right filename cited as a source. Passed on the first real run.
- Full suite: plain `pytest` → **57 passed, 2 deselected** (fast, offline — both new
  live tests correctly excluded by the marker gating set up in the previous
  increment); `pytest -m live` → **2 passed** (this one + retrieval's), confirmed
  Neon left clean (0 rows in all three tables) afterward. `ruff check` → clean.

## 2026-07-15 — Test-infra: gate live tests behind `pytest -m live`
- Problem: the retrieval increment's live Neon+Cohere test only checked whether
  `DATABASE_URL` was configured (via `get_settings()`, not raw `os.getenv`) — since it
  is, in this dev environment, that test ran on *every* plain `pytest` invocation and
  every local pre-push, silently making the "default" test run network-dependent
  again (slower, real Cohere API cost per run, fails on any network blip unrelated to
  actual code correctness). Flagged as a known trade-off in the previous entry;
  fixed properly here rather than left as a standing footgun.
- `backend/pyproject.toml`: registered a `live` marker
  (`markers = ["live: hits real Neon/Cohere, opt-in"]`) and set
  `addopts = "-m 'not live'"`, so the default `pytest` run always deselects anything
  marked `live` — no need to remember a flag every time.
- `tests/test_search.py`: added `@pytest.mark.live` to the real-Neon test, on top of
  (not instead of) its existing `@pytest.mark.skipif(not
  get_settings().database_url, ...)` — the marker controls whether it's *selected* by
  default, the skipif still guards against running in an environment with the `live`
  marker requested but no real `DATABASE_URL` at all (fails closed either way, rather
  than erroring).
- Verified both invocations directly rather than trusting the config: plain
  `pytest tests -q` → **49 passed, 1 deselected** (confirmed fast and offline — no
  Neon/Cohere connection attempted); `pytest -m live -q` → **1 passed, 49
  deselected** (confirmed it actually reaches real Neon + Cohere and passes).
  Confirmed Neon left clean (0 rows in `subjects`/`documents`/`document_chunks`)
  after the `-m live` run, same as every other live check this project has done.
- `ruff check` → clean (no code changes outside test/config files, so no behavior
  change to `app/` — this is purely how the test suite is invoked).

## 2026-07-15 — Retrieval: service.search_chunks (no HTTP endpoint, no Claude yet)
- `embedding.py`: refactored `embed_texts` to share a new private `_embed(texts,
  input_type)` with a new `embed_query(text) -> list[float]` — the query-side of
  Cohere's asymmetric model (`input_type="search_query"`, vs. `embed_texts`'
  `"search_document"`). Live-verified directly against the real Cohere API before
  trusting it (1024-dim vector back for a real question).
- `DocumentChunk.subject_id` added — denormalized from `Document`, same reasoning as
  the existing `owner_id` duplication: lets `search_chunks` filter by owner+subject
  directly on this table, no join needed on the retrieval hot path. Confirmed
  `document_chunks` was still empty on Neon (we've cleaned up every live test's rows
  all along) before adding it as a straight `NOT NULL` column, no backfill needed.
  Migration `ba1acb6a4b7c_add_subject_id_to_document_chunks`, applied to Neon;
  `create_document`'s chunk-creation loop updated to populate it.
- Before writing the query, read `pgvector.sqlalchemy.Vector`'s comparator source
  directly (`inspect.getsource(Vector.comparator_factory)`) rather than assuming —
  confirmed `.cosine_distance(other)` maps to the `<=>` operator exactly as the task
  specified.
- `service.search_chunks(session, owner_id, subject_id, query, top_k=8) ->
  list[tuple[DocumentChunk, float]]`: `_require_owned_subject` first (same pattern as
  every other function here — a bad `subject_id` should raise `SubjectNotFoundError`,
  not silently return nothing), then filters `owner_id`, `subject_id`, `embedding IS
  NOT NULL`. On Postgres, embeds the query and adds `ORDER BY
  DocumentChunk.embedding.cosine_distance(query_vector) LIMIT top_k`; returned score is
  `1 - cosine_distance` (higher = more similar). **Branches on
  `session.get_bind().dialect.name`**: `<=>` doesn't exist on SQLite, so off Postgres
  the function still applies every WHERE filter (making tenant/subject scoping
  unit-testable there) but skips ordering/scoring entirely (score `0.0` for
  everything) — confirmed the dialect name comes back as `"sqlite"` / `"postgresql"`
  as expected before relying on the branch.
- **Real bug, caught by the very first SQLite test I wrote for this**: a chunk stored
  with `embedding=None` was still coming back from an `embedding IS NOT NULL` filter.
  Traced it to `typeof(embedding)` returning `'text'` (not `'null'`) for that row —
  SQLAlchemy's `JSON` type (the SQLite fallback from the previous increment's
  `with_variant`) stores a Python `None` as the literal string `"null"` (a JSON null
  value), not an actual SQL `NULL`, unless `none_as_null=True` is set. Fixed:
  `JSON(none_as_null=True)` in `models.py`. Real Postgres's `Vector` type never had
  this problem — a `None` there was already a genuine column `NULL` — so this was
  purely a SQLite-fallback-specific gap that the previous increment's tests never
  happened to exercise (they only ever stored real vectors, never `None`, on that
  column).
- **Second bug, this one in my own test helper, not production code**: after fixing
  the above, one SQLite test still failed. `_make_chunk(embedding=None)` was silently
  getting replaced by the helper's default 0.1-vector, because
  `if embedding is None: embedding = <default>` can't tell "caller didn't pass this
  argument" apart from "caller explicitly passed `None`" — both look identical to that
  check. A throwaway reproduction script (constructing `DocumentChunk` directly,
  bypassing the helper) had "confirmed the fix worked" earlier for exactly this
  reason: it never went through the buggy helper at all. Lesson: when a test result
  contradicts a manual reproduction, re-run the *actual* failing test path, not a
  similar-looking substitute — the two aren't guaranteed equivalent, and weren't here.
  Fixed with a proper `_UNSET` sentinel object as the parameter default instead of
  `None`.
- Tests:
  - `tests/test_embedding.py` (+2): `embed_query`'s call args (`input_type=
    "search_query"`, single-text list) and its own `EmbeddingError` wrapping path.
  - `tests/test_search.py` (new, 5 SQLite tests + 1 live): owner+subject match
    required (a sibling subject under the same owner is excluded; a different owner's
    subject of the same *name* is excluded too — name collisions don't leak data);
    chunks with no embedding excluded; `top_k` truncates; a nonexistent `subject_id`
    raises `SubjectNotFoundError`. Cohere mocked throughout (`embed_query` patched at
    the `documents_service` level), network-free.
  - **Live test against real Neon**, gated with `@pytest.mark.skipif(not
    get_settings().database_url, ...)` — deliberately checking `get_settings()`, not
    `os.getenv("DATABASE_URL")` directly, since the latter wouldn't see a value that
    only exists in `backend/.env` (pydantic-settings reads the file itself; it doesn't
    populate `os.environ`). Creates 3 real documents on genuinely different topics
    (photosynthesis / volcanoes / HTML) with real Cohere embeddings throughout, then
    asserts a photosynthesis-themed query ranks the photosynthesis document's chunk
    first with strictly descending similarity scores — this is a real semantic-ranking
    assertion, not just a plumbing check. Passed on the first real run. Cleans up in a
    `try`/`finally` (chunks → documents → subject, correct FK order) so it leaves
    nothing behind in Neon whether it passes or fails.
  - **Trade-off worth flagging**: since `DATABASE_URL` is configured in this dev
    environment, this live test now runs on *every* `pytest tests` invocation,
    including the local pre-push git hook — meaning routine test runs here make a
    real Cohere + Neon round trip (slower, tiny real API cost, requires network). This
    is exactly what the task asked for ("skip if no DATABASE_URL"), and CI has no
    `DATABASE_URL` secret configured so it skips automatically there — but it's a
    real behavior change from every previous increment's fully network-free test
    suite, worth knowing if `pytest`/`git push` ever feels slower or fails on a
    network blip unrelated to any actual code change.
- Full suite: **50 passed** (7 new: 2 embedding + 5 search); `ruff check` → clean.

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
