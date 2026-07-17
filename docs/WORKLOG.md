# Worklog

Log of completed work (newest first). Each entry: what was done, tests, commit.

## 2026-07-17 — Plan tiers + usage-limit enforcement (Phase 4 billing foundation)
- Polar itself is blocked on the user's account/API keys, but the **entitlement layer**
  — which plan an owner is on and enforcing that plan's caps — is independent of the
  payment provider, so it's built now. Polar later just upserts one `UserPlan` row from
  its webhook; nothing else changes. No Polar SDK, no secrets, no plan-change endpoint
  in this increment.
- **`feat(billing)` — models + migration**: `UserPlan` (`owner_id` PK, plan enum,
  `updated_at`); **absence of a row = Free**, never an error, so a brand-new user with
  no billing row still uses the app up to the Free cap.
  - `GenerationUsage` (`owner_id`, `day`, `kind`, `count`; unique on the triple) counts
    generation **events**. This was the increment's main open design question, and the
    answer isn't the obvious one: counting existing rows by `created_at` *looks* free
    but is wrong, because rows don't map to events 1:1 — one `generate_quiz` writes one
    `Quiz` row (countable), but one `generate_flashcards` writes *N* `Flashcard` rows, so
    counting those would charge a single 10-card generation as 10 against a 20/day cap.
    A dedicated counter records what the limit actually means, has bounded growth (≤2
    rows/owner/day, not one per event), and stays correct if either module's
    rows-per-generation ratio changes.
  - Migration `48c8dee79a2c` applied to Neon; enum labels verified lowercase via
    `pg_enum` (the `values_callable` fix this codebase already established), unique
    constraint + indexes confirmed, `alembic check` clean. Also **fixed a latent gap
    rather than copying it**: autogenerate's `downgrade()` drops the tables but not the
    Postgres enum *types* `create_table` implicitly created, so a downgrade would leave
    them behind and the next upgrade would fail with "type already exists". Added
    explicit `DROP TYPE IF EXISTS` — the pre-existing `documentstatus` migration has
    this same gap, noted in the migration rather than repeated.
- **`feat(billing)` — service + router**: `billing.service` **owns all quota counting**;
  the four guarded modules each gained exactly one guard call and zero counting logic.
  Every cap lives in one documented `LIMITS` dict (Free 3/10/20, Pro 50/200/200,
  Business unlimited via `None` — which short-circuits the count query rather than
  comparing against a huge sentinel), so tuning a tier is a one-line change. **The user
  should confirm/adjust those numbers** — they're the task's defaults.
- **Tenant scoping is the security crux of this module**, more than anywhere else: a
  usage count that read across owners would let one user's activity consume — or
  silently bypass — another's quota. Every count filters `owner_id` directly (each table
  already carries its own denormalized `owner_id`, so it's a plain equality filter, never
  a join that could go wrong), and the per-subject document count filters `owner_id`
  **and** `subject_id` — either alone is wrong in a different way (subject-only would be
  a cross-tenant read if a subject_id ever leaked; owner-only would count the wrong
  subject's documents). Asserted per-cap in the tests.
- **Ordering contract, decided and documented in the code** (the task's core pitfall):
  `ensure_can_*` runs at the START of each create path — before the R2 upload in
  `create_document`, before the Claude call in both generators, before any row is
  written — so a rejected request does no billable work and persists nothing.
  `record_generation` **stages the increment without committing**, so the caller's
  existing `session.commit()` persists counter + generated rows in the *same
  transaction* (neither can land without the other, so the counter can't drift), and it
  only runs *after* generation succeeded — a failed Claude call doesn't burn the user's
  daily quota. The check/increment race at the exact cap boundary is documented as an
  accepted ±1 overshoot on a soft cost-bounding cap, rather than paying for
  `SELECT ... FOR UPDATE` contention on every generation.
- **Days are UTC** (`_utc_day`) with an injectable `now` throughout — a local-time
  boundary would depend on server timezone and be flaky/untestable, exactly as the task
  warned.
- **`PlanLimitExceededError` → 402 via one app-wide exception handler** in `main.py`,
  not the same `except` block copy-pasted into four routers. The mapping is identical
  everywhere, so one handler keeps those routers thin (the increment's own rule) and any
  future guarded path gets it for free; per-router try/except stays the pattern for
  *module-specific* exceptions, which genuinely differ per route. The body names the
  limit + cap in prose **and** carries `limit`/`plan`/`cap` as fields, so a frontend can
  act on it without parsing English.
- `GET /billing/plan` returns plan + limits + usage (`subjects`, `generations_today`) so
  the UI can render "2 of 3 subjects used". `max_documents_per_subject` deliberately has
  no account-wide usage number — it's a per-subject cap, and the per-subject count
  already comes from `GET /subjects/{id}/progress`. **No plan-change endpoint**: that's
  the provider's job, and a self-serve "set my own plan" route would be an entitlement
  bypass.
- Tests: `test_billing.py` (26, offline/SQLite, no mocking — nothing external here).
  Every cap asserted **exactly at its boundary** (Nth allowed / N+1th raises with the
  right limit+plan+cap); default-Free-when-no-row; Pro lifting a cap and Business
  unlimited; the document cap being per-subject not per-account; the generation cap
  counting quiz + flashcards **together**; `record_generation` creating-then-incrementing
  one row per slot (not one per event); its no-commit contract asserted by rolling the
  caller's transaction back and confirming the counter rolled back too; the UTC-day reset
  pinned with an injected `now` (exhausted at 23:59, fresh one second past midnight) and
  asserted day-bucketed rather than a rolling 24h window; **tenant isolation per cap**;
  and over HTTP — a 402 with the right fields, a rejected create persisting nothing, and
  inserting a Pro row (what Polar's webhook will do) lifting the cap immediately.
  Backend **244 passed** (9 deselected live, up from 218/9), `ruff` clean. **The 218
  pre-existing tests needed no changes** — none of them exceeded a Free cap, which is
  itself a useful signal that the defaults aren't absurdly tight.
- **Live-verified against real Neon**, using a throwaway owner id so the real account's
  data was never touched (confirmed before and after): a no-row owner defaulted to Free
  with cap 3 → created 3 subjects (all 201) → `GET /billing/plan` reported
  `subjects: 3` → the 4th returned **402** with
  `{"limit":"subjects","plan":"free","cap":3}` and "You've reached your free plan limit
  of 3 subjects. Upgrade your plan to continue." → confirmed the rejected create
  persisted nothing (still exactly 3) → inserted a Pro `UserPlan` row, simulating the
  future Polar webhook → the same request that had just 402'd returned **201**. Every
  row cleaned up; the two real users' subjects untouched. (Throwaway script, not
  committed.)
- Phase 4 status: Progress (backend + frontend) and the entitlement layer are done. The
  Polar **payment wiring** is the one blocked item; a billing frontend (usage meters /
  upgrade prompts) is a separate, unblocked next increment.

## 2026-07-17 — Progress dashboard frontend (closes Phase 4's Progress half)
- The UI for the Phase 4 progress backend: a per-subject progress page and an overall
  `/dashboard`. Polar billing (the other Phase 4 item) is still blocked on the user's
  account/keys — unaffected by this increment.
- **`chore(frontend)`**: regenerated `schema.d.ts` — `SubjectProgress`/
  `OverallProgress`/`DocumentStatusCounts`/`FlashcardProgress` + the 2 routes now typed.
- **Loaded the `dataviz` skill before writing the mastery breakdown** — it's a data
  visualization by the skill's own trigger criteria, so this happened before any chart
  code or color choice, not after. The breakdown ended up as a **status-encoded**
  segmented bar rather than a fresh categorical palette: `new`/`learning`/`mature` map
  onto the app's pre-existing semantic tokens (`muted-foreground`, `primary`,
  `success`) — a design system's already-chosen status tokens are precisely the kind of
  parameter the skill's method expects to receive, not re-derive from scratch. Every
  segment still gets a visible label + count in the legend beneath the bar (never color
  alone — one of the skill's non-negotiables, satisfied by construction here since the
  legend was always going to exist for accessibility reasons anyway).
- **`feat(frontend)` — helpers**: `lib/flashcardMastery.ts` (`masteryRows`,
  `percentMature`) and `lib/documentProgress.ts` (`documentStatusRows`) turn the
  backend's response into display rows — **neither recomputes anything**, they only
  format the `new`/`learning`/`mature`/`ready`/`pending`/`failed` counts the API already
  computed, so the UI can never silently disagree with the backend's bucket math (the
  same "don't re-derive the source of truth" principle the task called out explicitly
  as a pitfall). 10 vitest tests, including the empty-deck/zero-count cases returning
  `0` rather than `NaN`/`Infinity`.
- **`feat(frontend)` — shared component**: `components/progress-stats.tsx` — stat
  tiles, a document-status badge row (reusing the same ready/pending/failed →
  badge-variant mapping as the existing `documentStatus.ts`), and the mastery bar. Used
  by both new pages so they can't drift apart in how they render the same
  `documents`/`flashcards`/`quiz_count` shape.
- **`feat(frontend)` — pages**:
  - `subjects/[subjectId]/progress/page.tsx` — same states as every other
    subject-scoped page: "Subject not found" checked via `subjectQuery.isError` first
    (matching the quiz/flashcards pages' pattern exactly, not a generic "couldn't load
    progress" for a 404), loading, and — the empty-account case the task specifically
    called out — a friendly "Nothing to show yet" nudge instead of an all-zeros stat
    grid, when the subject genuinely has no documents/flashcards/quizzes.
  - `dashboard/page.tsx` — `subject_count === 0` renders a "Welcome to StudyMate / get
    started" card instead of a broken-looking zeroed dashboard. **Added `/dashboard` to
    the Clerk middleware matcher** (it was `/subjects(.*)` only) — without this the
    page would render but its API calls would 401, since nothing forces a session on
    an unprotected route. Linked from the Subjects page header (beside `UserButton`)
    and from the home page for a signed-in visitor.
  - Subject-detail page gains a "Progress" (outline) button alongside
    Flashcards/Quizzes/Ask.
- **Real API-surface gap caught by `tsc`, not assumed away**: `SignedIn`/`SignedOut`
  don't exist in the installed `@clerk/nextjs` (`7.5.18`) — `tsc` rejected the import
  immediately. Read the package's own `.d.mts` declarations rather than guessing a
  workaround: this version unified them into a single `<Show when="signed-in"
  fallback={...}>` component (`when` also takes `"signed-out"`, an authorization
  descriptor, or a predicate function). Used that instead of downgrading or
  hand-rolling an auth check.
- Verified: `tsc --noEmit` clean, `eslint` clean, **90 passed** (21 files, up from
  80/19), `npm run build` succeeds (both new routes compile). `/` moved from a static
  to a dynamic prerender once it needed `<Show>`'s auth-aware rendering at request
  time — expected given the change, not a regression to chase.
- **Live-verified**: still no browser available in this environment (the same standing
  gap on every frontend page here), so this drove **the exact real HTTP endpoints and
  payload shapes both new pages call** against real Neon data — the same real
  subjects/documents/flashcards/quizzes already used to live-verify the backend
  increment. Confirmed both `SubjectProgress` and `OverallProgress` match the shape
  `ProgressStats`/`masteryRows`/`documentStatusRows` expect, and specifically that
  `new + learning + mature == total` holds against the real payload — the exact
  partition invariant the stacked bar's rendering assumes. Read-only throughout
  (throwaway script, not committed).
- Phase 4's Progress half is now fully done (backend + frontend). Polar billing remains
  the one blocked item; everything else in Phase 4 is complete.

## 2026-07-17 — Progress tracking backend: read-only aggregation (Phase 4 start)
- Phase 4 is "Progress + Polar billing". Polar needs the user's account/API keys (not
  yet provided — blocked, same pattern as R2/Inngest were before). Did Progress first:
  a read-only rollup of a student's existing data into per-subject and overall
  study-progress stats.
- **`feat(progress)`**: new `app/modules/progress/` — **no models**, mirroring `ask`'s
  shape (it also owns no tables of its own). Every query reads
  `Document`/`Flashcard`/`Quiz` directly, filtered by `owner_id` alone — each of those
  tables already carries its own denormalized `owner_id` column (the same
  defense-in-depth tenant-scoping used everywhere in this codebase), so "only this
  caller's data" is a plain equality filter, no join through `Subject` needed at all.
  Verified the exact `session.exec(select(func.count())...).one()` (returns a plain
  `int`) and grouped-row (`(status, count)` tuples) return shapes empirically before
  writing the real queries — first `func.count()` usage anywhere in this codebase.
  - `_document_status_counts`: one `GROUP BY` query for ready/pending/failed — the
    natural SQL shape for "counts by category," not three separately-filtered COUNTs.
  - `_flashcard_progress`: `due` (`due_at <= now`, `now` overridable — same
    deterministic-clock pattern as `flashcards_service.list_due_flashcards`), and a
    `new`/`learning`/`mature` bucketing that only needs 3 queries, not 4: `new`
    (`repetitions == 0 AND last_reviewed_at IS NULL` — never reviewed at all) and
    `mature` (`interval_days >= MATURE_INTERVAL_DAYS_THRESHOLD`, = 21, documented —
    matches Anki's own young/mature cutoff) are mutually exclusive by construction (a
    card only gets a non-zero interval via a review, and a review always sets
    `last_reviewed_at`), so `learning = total - new - mature` is an exact partition
    subtraction — and it correctly counts a *lapsed* card (repetitions reset to 0 by a
    low SM-2 grade, but `last_reviewed_at` still set from before) as `learning`, not
    `new` again — the one bucket rule that's easy to get wrong. `due` is a separate,
    orthogonal COUNT (new/learning/mature cards can each independently be due or not).
  - **Quiz count is quizzes *generated*, not a score history** — documented as a
    deliberate scope decision, not an oversight: quiz attempts/scores aren't persisted
    anywhere (grading is entirely client-side — nothing is ever submitted back to the
    server, per the quiz module's answer-key decision). A `QuizAttempt` model +
    submission endpoint would be needed to track performance; noted as a follow-up in
    `docs/PROGRESS.md`, not built here — keeps this increment focused on aggregating
    data that already durably exists.
  - `get_subject_progress` calls `require_owned_subject` before any aggregate runs — a
    progress endpoint leaking *counts* for a subject the caller can't otherwise see is
    still a tenant leak. `get_overall_progress` is owner-scoped only (no subject
    filter), summing across every subject the caller owns.
  - `router.py`: `GET /subjects/{subject_id}/progress` + `GET /progress`, same
    subject-scoped-`router` / flat-`overall_router` split as `ask.router`'s
    `router`/`conversations_router`. Wired into `main.py`.
- Tests: `test_progress.py` (10, offline/SQLite) — **the only module test file so far
  with zero mocking**, since progress touches no Claude/Cohere/R2/Inngest at all, just
  DB reads. A hand-computed 5-flashcard fixture (documented inline with its expected
  bucket math) exercises every SM-2 bucket including the lapsed-card case at once;
  covers a zeroed subject with no data, a sibling subject's data excluded from a
  per-subject rollup, 404s for missing/unowned subjects, overall progress correctly
  summing multiple subjects, a zeroed overall for no subjects, and — the classic leak
  point per the task — **another owner's identical dataset never bleeding into
  `/progress`, checked from both directions** (as the original caller, and as the
  other owner). One direct service-level test pins `get_subject_progress`'s
  overridable `now`; the HTTP-level tests use wall-clock-relative fixture dates since
  the router itself has no client-suppliable `now` parameter (not sensible for an
  HTTP caller to control "now" for a due-count). Caught one real test bug along the
  way (not production code): the first version of the fixture used fixed 2026-01-01
  dates for "past"/"future", which broke because the *router's* `due` calculation
  uses real wall-clock time (2026-07-17 in this session), so every fixed fixture date
  registered as "due" — fixed by making the fixture dates relative to
  `datetime.now(UTC)` instead. Backend **218 passed** (9 deselected live, up from
  208/9 — no live test needed, no Postgres-specific aggregate here), `ruff` clean.
- **Live-verified against real Neon data**: hand-computed the true aggregates via
  direct SQL against the user's own real Clerk-authenticated data (not seeded by this
  verification) — one real subject with 1 ready document, 10 flashcards (all new, all
  due), and 2 quizzes; a second real subject with nothing uploaded yet (all zero) —
  then confirmed `GET /subjects/{id}/progress` (both subjects) and `GET /progress`
  (summed across both) return those exact numbers, plus a 404 for an unowned subject
  id. Entirely read-only — no data created, modified, or deleted. (Non-issue caught
  along the way: an initial direct-SQL check briefly returned stale/lower counts right
  after connecting — a Neon serverless cold-start read-consistency blip, not a bug;
  re-querying fresh immediately before each assertion resolved it.)
- Phase 4's Progress half is done; Polar billing is blocked on the user's account/keys.
  The progress *frontend* (a dashboard) is the next increment.

## 2026-07-17 — Flashcards frontend: generate + SM-2 review session (closes Phase 3)
- The UI for the Phase 3 flashcards backend. Students generate cards and run an SM-2
  review session with the four Anki-style grade buttons. Consumes the already-typed
  `/subjects/{id}/flashcards[/due]` + `/flashcards/{id}[/review]` routes.
- **`chore(frontend)`**: regenerated `schema.d.ts` — `FlashcardRead`/
  `FlashcardGenerateRequest`/`ReviewRequest` + the 4 routes now typed.
- **`feat(frontend)` — helpers**: `lib/flashcardError.ts` (`friendlyFlashcardError`,
  mirrors `friendlyQuizError` — 422 no material, 502 generation failure, off the real
  `response.status`). `lib/gradeButtons.ts` — the one place the 0-5 SM-2 contract to
  `POST /flashcards/{id}/review` is pinned on the frontend: `GRADE_BUTTONS` (Again=1,
  Hard=3, Good=4, Easy=5 — Anki-style four buttons, deliberately not six raw numbers
  dumped on the learner) and `isLapseGrade` (mirrors the backend's
  `sm2.PASSING_GRADE=3` — only Again is a lapse). `lib/reviewProgress.ts` — pure
  session position/remaining/completion from a fixed total + current index, no
  fetching. 15 vitest tests across the three.
- **`feat(frontend)` — pages**:
  - `flashcards/page.tsx` — generate form (`num_cards` 1-50, default 10) + card list.
    Generate guards double-submit, shows "Generating…"; delete mirrors the existing
    delete-document/delete-quiz pattern. A live "Review (N)" button (its own `/due`
    query) links to the session, disabled when nothing's due.
  - `flashcards/review/page.tsx` — **fetches `/due` once and steps through that fixed
    snapshot by index**, not a live-refetched list — the key design decision here: if
    the due-count query in the background refetches after a card is graded (React
    Query's default behavior), that card disappearing from a *live* `/due` result must
    not reshuffle which card the learner is looking at mid-session. `reviewProgress.ts`
    computes position/remaining against that fixed snapshot. Shows the front only;
    "Show answer" reveals the back; the four grade buttons `POST` the review and
    advance — Again uses `destructive`, Easy uses the `--success` token (added in the
    quiz increment) via a `className` override on the `outline` variant (safe under
    `twMerge`, confirmed no class conflict). Complete/empty states are distinguished:
    "No cards due right now" (nothing to review) vs. "Done for now! You reviewed N
    cards" (session finished).
  - Subject-detail page: a "Flashcards" (outline) button beside Quizzes/Ask.
- Verified: `tsc --noEmit` clean, `eslint` clean, **80 passed** (19 files, up from
  65/16), `npm run build` succeeds (both new routes compile). The build's earlier
  "stale `.next` shared with the dev server" gotcha (hit in the quiz increment) was
  avoided this time by stopping `next dev` and clearing `.next` before building.
- **Live-verified**: still no browser available in this environment (the same standing
  gap noted on every frontend page in this project), so this drove **the exact real
  HTTP endpoints and payload shapes the pages themselves call** through the full real
  stack instead of a browser click-through — real Inngest Dev Server + real
  R2/Neon/Cohere/Claude: upload → `ready` → generate 4 real cards → confirmed all due
  immediately (exactly what the list page's `Review(4)` badge reflects) → graded one
  card with each of the four buttons in turn → confirmed Again (grade 1) resets
  `repetitions` to 0 while Hard/Good/Easy (3/4/5) all advance it to 1 and every grade's
  `due_at` moved forward → confirmed all four graded cards correctly dropped out of a
  fresh `/due` fetch (0 remaining), exactly what drives the review page's empty state.
  Cleaned up via real `DELETE`s; Neon **and** R2 both confirmed clean afterward
  (throwaway script, not committed).
- Phase 3 (Flashcards + SM-2) is now complete — backend (previous entry) + frontend
  (this one). Phase 4 (progress tracking + Polar billing) is next per `docs/plan.md`.

## 2026-07-17 — Flashcards backend: SM-2 scheduling + Claude tool-use generation (Phase 3 start)
- First Phase 3 feature. New `app/modules/flashcards/` (models + sm2 + generation +
  service + schemas + router), same established split as documents/ask/quiz.
- **`feat(flashcards)` — sm2.py + models + migration**: `sm2.review(grade, state, now)`
  is a **pure function** — no DB, no I/O, no `datetime.now()` buried inside; `now` is
  always caller-supplied, which is what makes every rule deterministically testable.
  Implements canonical SuperMemo SM-2: `grade < 3` resets `repetitions`/`interval_days`
  to relearn, but **does not reset `ease_factor`** — the ease-update formula (`ef' = ef +
  (0.1 - (5-q)*(0.08 + (5-q)*0.02))`) applies unconditionally, on every review, so a
  lapse only nudges ease down rather than wiping out a card's whole easing history. This
  is the exact bug the task called out, and it's cheap to get wrong if the reset and the
  ease-update get bundled into the same `if grade < 3` branch — kept deliberately
  separate here. `grade >= 3`: rep 1 → 1 day, rep 2 → 6 days, rep *n* →
  `round(prev_interval * ease_factor)`. `ease_factor` floored at `1.3`. `Flashcard`
  model: `subject_id` FK, `owner_id`-scoped, `front`/`back`, SM-2 state columns. New
  cards default `due_at=now`/`repetitions=0`/`ease_factor=2.5`/`interval_days=0` — due
  immediately. Migration `b27704cd2174`, applied to Neon, confirmed via
  `information_schema`; `alembic check` clean.
- **`feat(flashcards)` — generation.py**: mirrors `quiz/generation.py` exactly
  (DECISIONS.md #5, tool-use structured output, not `json.loads`): forced
  `record_flashcards` tool, strict schema, defensive `_parse_flashcards` (rejects an
  empty-string front/back even though it's schema-valid), `FlashcardGenerationError` on
  any malformed/empty/API failure, missing key → bare `RuntimeError`, multilingual.
- **`feat(flashcards)` — service + routes**: `generate_flashcards` verifies ownership,
  samples material (reused `sample_subject_chunk_texts`, no re-embedding), generates,
  persists atomically. `review_flashcard`/`delete_flashcard`/`get_flashcard` are
  **owner-scoped by id alone** — same pattern as `documents.service.get_document_by_id`
  — since neither review nor delete carries `subject_id` in its URL (mirrors
  `ask.router`'s subject-scoped-`router` / flat-`conversations_router` split: here,
  `router` = generate/list/`/due`, `flashcards_router` = review/delete).
  `review_flashcard` validates `grade` 0-5 before calling `sm2.review`
  (`InvalidGradeError`) — defense-in-depth; `ReviewRequest.grade`'s Pydantic `ge=0, le=5`
  already rejects a bad grade at the HTTP boundary before this line is ever reached.
  `list_due_flashcards`/`review_flashcard` both take an overridable `now` so neither
  depends on wall-clock timing for correctness. Wired into `main.py` + `alembic/env.py`.
- Tests: `test_sm2.py` (18, pure/deterministic) — every rule from the algorithm gets its
  own assertion, including the specific lapse-decrements-but-doesn't-reset-ease case and
  grade 4 landing exactly on the formula's zero-crossing. `test_flashcard_generation.py`
  (9, Anthropic client mocked directly). `test_flashcards.py` (22 SQLite integration +
  1 live): generation mocked at the service boundary offline, chunks seeded directly (no
  R2/Inngest needed); covers generate/list/due/review/delete tenant scoping, the 422/502
  paths (with nothing persisted on failure), due-date filtering, and review actually
  advancing/resetting the schedule correctly. One test bug caught and fixed along the
  way (not a production bug): the live test's "due_at advanced" assertion initially
  compared a card to itself, because `review_flashcard` looks the card up in the same
  session and mutates the identity-mapped object in place — fixed by snapshotting the
  pre-review `due_at` as a plain value first. Backend **208 passed** (9 deselected live,
  up from 159/8), `ruff` clean.
- **Live-verified end-to-end** two ways: (1) the `-m live` test — real Neon + Cohere +
  Claude tool-use generates well-formed cards, a real review advances the schedule,
  cleanup removes both the Neon rows *and* the R2 object the uploaded document created
  (confirmed via `list_objects_v2`) — **the existing quiz/search live tests leave that
  R2 object orphaned; this one doesn't repeat the gap**, per the task's explicit ask.
  (2) The full real stack — real Inngest Dev Server + real R2/Neon/Cohere/Claude: real
  HTTP upload → `pending` → `ready` in ~5s → `POST /flashcards` → 4 well-formed cards,
  all due immediately → a real `POST /flashcards/{id}/review` correctly advanced
  `repetitions`/`interval_days`/`due_at`, and the reviewed card correctly dropped out of
  `GET /due` afterward while the other 3 remained. Cleaned up via real `DELETE`s; Neon
  **and** R2 both confirmed clean afterward (throwaway script, not committed). Not
  browser-tested (no browser/Clerk auth in this environment) — the flashcards frontend
  is the next increment.

## 2026-07-17 — Hybrid retrieval: Postgres FTS + vector, fused with RRF (closes Phase 2)
- Added the lexical arm to retrieval and fused it with the existing vector arm via
  Reciprocal Rank Fusion, before the Cohere Rerank stage. DECISIONS.md #4 requires FTS
  to live in Postgres (not a per-query in-memory BM25 rebuild like Lexara).
- **`feat(backend)` — FTS in Postgres**: migration `066f42dbed80` adds
  `document_chunks.text_search_vector` as a `GENERATED ALWAYS AS (to_tsvector('simple',
  text)) STORED` column + a GIN index over it.
  - Generated/stored, so Postgres computes the tsvector once per row on write **and for
    every existing row when the column is added** — no separate backfill (the pitfall);
    it regenerates automatically when `text` changes. No trigger, no app code to keep it
    in sync.
  - `'simple'` config on purpose: multilingual app, and `simple` does no
    language-specific stemming/stopword removal (`english` would mangle non-English
    terms). The two-arg form is IMMUTABLE, which a generated column requires — the
    one-arg `to_tsvector(text)` depends on a session GUC (STABLE) and is rejected.
  - Managed in **raw SQL, not on the `DocumentChunk` SQLModel** — a `tsvector` generated
    column would break the SQLite test engine's `create_all` (no tsvector type, no
    `to_tsvector`). To stop autogenerate from then seeing a DB column absent from the
    model and proposing to drop it, `alembic/env.py` gained an `include_object` filter
    that excludes this Postgres-only column + index. Verified with `alembic check` →
    "No new upgrade operations detected". Applied to Neon; confirmed the generated column
    (`is_generated=ALWAYS`, expr `to_tsvector('simple', text)`) via `information_schema`
    and the GIN index via `pg_indexes`.
- **`feat(backend)` — hybrid `search_chunks` + RRF**: the Postgres branch now runs two
  owner+subject-scoped arms — the existing pgvector cosine arm and a new lexical arm
  (`websearch_to_tsquery`/`ts_rank` over the GIN-indexed tsvector; `websearch_to_tsquery`
  tolerates arbitrary user input without raising; config matches the column's `'simple'`,
  confirmed against Neon before wiring) — and fuses them with `rrf.py`'s
  `reciprocal_rank_fusion`. RRF is a pure, DB-free helper: it fuses on **rank position**
  (`score = Σ 1/(k+rank)`, `k=60` from the Cormack et al. paper), because cosine distance
  and `ts_rank` are on different scales and can't be added directly — the exact reason
  RRF is the standard here. The fused pool is bounded to `RERANK_CANDIDATE_POOL` (one
  Rerank call, same cost profile as before) and handed to the unchanged `_rerank_candidates`
  Cohere stage; the RRF score rides along so a rerank *failure* falls back to fused order.
- **Guarantees preserved**: both arms carry `owner_id + subject_id` — the FTS arm is a
  brand-new place a cross-tenant leak could hide, so the filter is not optional there;
  the SQLite branch is untouched (FTS and `<=>` are Postgres-only, so off Postgres it
  still returns the filtered-but-unranked chunks) → the offline scoping tests pass
  unchanged; graceful rerank fallback intact; Ask (stream + non-stream) needed **no
  change** — it goes through the same `search_chunks` entry point.
- Tests: `test_rrf.py` (9, offline/pure — single-list order preserved, an item in both
  arms outranks a single-arm item, agreed-top wins, one/both/no arms empty, deterministic
  tie-break by first appearance, the exact `1/(k+1)` score, and `k` dampening the
  rank-1-vs-2 gap). `test_search.py`: SQLite scoping tests unchanged (FTS skipped off
  Postgres) + a new live test asserting the hybrid path surfaces an exact keyword/code
  match (`ISO-9001`) as the top result — the FTS arm's whole reason for existing — with
  the FTS arm owner+subject-scoped. Backend **159 passed** (8 deselected live, up from
  150/7), `ruff` clean.
- **Live-verified** against real Neon + Cohere + Claude: the live search tests (hybrid
  returns the exact-keyword chunk first; on-topic still ranks first) and both live **Ask**
  tests (non-stream + streaming) — grounded, correctly-cited answers end-to-end through
  the hybrid path. Neon confirmed clean afterward.
- Phase 2 (Quiz + FTS hybrid) is now complete; Phase 3 (Flashcards + SM-2) is next.

## 2026-07-17 — Quiz frontend (generate / take / review / delete)
- The UI for the Phase 2 quiz backend. Students can generate a quiz for a subject, take
  it as a real self-test, reveal the score + explanations, and delete it. Follows the
  established page pattern (client component, `useApiClient` + TanStack Query, shadcn
  Base-UI, `docs/FRONTEND.md`), consuming the already-typed `/subjects/{id}/quizzes`
  routes (`schema.d.ts` was regenerated in the backend increment — no hand-edits here).
- **`feat(frontend)` — helpers + token**: `lib/quizError.ts` (`friendlyQuizError` maps
  the generate endpoint's real statuses — 422 no material → an actionable "upload a
  document and wait" message, 502 → retryable — off `response.status`, since these
  hand-raised codes aren't in the generated typed error shape, same as
  `friendlyUploadError`). `lib/quizScore.ts` — pure grading with no React and no reveal
  (`allAnswered` gates submit, `isCorrect`, `scoreQuiz`); the page owns reveal state,
  this only computes. Added a semantic `--success`/`--success-foreground` token (OKLCH,
  both themes, registered in `@theme inline`) per FRONTEND.md's "add `--success` when
  needed" so correct answers use a success token, not hardcoded green; wrong uses the
  existing `destructive`. 14 vitest tests across the two helpers.
- **`feat(frontend)` — pages**:
  - `quizzes/page.tsx` — quiz list + generate form (optional title, `num_questions`
    1–20 clamped client-side, default 5). Generate **guards against double-submit**
    (`disabled={isPending}` + an `isPending` check in the submit handler) and shows a
    "Generating…" state — it's a live Claude round-trip of a few seconds. Delete mirrors
    the delete-document flow exactly (`window.confirm`, destructive icon button, checks
    `error` not `data` since a 204 leaves `data` undefined, invalidates the quizzes
    query on success). Each quiz row links to its take view.
  - `quizzes/[quizId]/page.tsx` — take/review. **`correct_index` is never used to style
    anything before the user reveals** (held client-side, compared only when they hit
    "Check answers"), so it's a genuine self-test, not an answer sheet — the key
    pitfall. "Check answers" is gated by `allAnswered`; on reveal the options lock, the
    correct one is marked with the `--success` token + a check icon and any wrong pick
    with `destructive` + an x icon (color always paired with an icon/label per
    FRONTEND.md rule 2.5), explanations appear, the score comes from `scoreQuiz`, and
    "Try again" resets answers + reveal.
  - Subject-detail page gains a "Quizzes" (outline) button beside the existing "Ask"
    button. Middleware already matches `/subjects(.*)` — no route-protection change.
- **Build gotcha (not a code bug)**: `npm run build` first failed collecting page data
  for the Clerk sign-in/sign-up catch-all routes — the concurrently-running
  `npm run dev` server was sharing `.next`. Stopping the dev server and clearing
  `.next` fixed it; the clean build succeeds with both new quiz routes compiled.
- Verified: `tsc --noEmit` clean, `eslint` clean, **65 passed** (16 files, up from
  51/14), `npm run build` succeeds. Not click-tested in a real browser (no browser /
  real Clerk auth in this environment — the same standing gap as every other frontend
  page in this project); the quiz *API* the UI drives was already live-verified
  end-to-end through the real stack in the backend increment, and `tsc` against the real
  regenerated `schema.d.ts` guarantees the UI consumes those exact shapes.

## 2026-07-17 — Quiz generation via Claude tool-use structured output (Phase 2 start)
- First Phase 2 feature and the codebase's first **structured-output** integration.
  DECISIONS.md #5 mandates quiz JSON via Claude tool-use, not `json.loads` on free text.
  New domain module `app/modules/quiz/` (router + service + schemas + models +
  generation), same established split as documents/ask.
- **Confirmed the tool-use API shape before writing any code** — introspected the
  installed anthropic SDK (`0.116.0`): `messages.create(tools=[{name, description,
  input_schema}], tool_choice={"type":"tool","name":...})`, response has
  `stop_reason == "tool_use"` and a `content` block with `.type == "tool_use"` whose
  `.input` is the API-validated dict. Verified with a real one-off call (2 MCQs came
  back well-formed) rather than assuming.
- **`feat(quiz)` — models + migration**: `Quiz` (subject_id FK, owner_id-scoped, title?)
  + `QuizQuestion` (quiz_id FK, owner_id, question, options as NOT-NULL JSON,
  correct_index, explanation?, order). Plain FK columns, no ORM cascade (codebase
  style). Migration `5ffe4bd447ff`, applied to Neon, confirmed via `information_schema`
  (`options` NOT NULL). Registered both models in `alembic/env.py`.
- **`feat(quiz)` — generation.py**: `generate_quiz_questions(excerpts, num_questions)`
  forces the `record_quiz` tool via `tool_choice` and reads the structured tool_input
  back. Strict `input_schema` (question, options[], correct_index, explanation;
  `additionalProperties: false`, all required). Defensive validation on the parsed
  input → `QuizGenerationError` on anything malformed: no tool_use block (e.g. hit
  max_tokens), empty questions, <2 options, non-string/empty option, an out-of-range
  `correct_index` (schema-valid integer but would break grading), and a bool
  masquerading as an int (bool is an int subclass in Python). Missing
  `ANTHROPIC_API_KEY` → bare `RuntimeError`; API/network failure → `QuizGenerationError`.
  Multilingual: prompt says write in the source material's language. `max_tokens` scales
  with `num_questions`, bounded at 8192.
- **`feat(quiz)` — service + routes**: `generate_quiz` verifies subject ownership,
  samples the subject's material, generates, and persists Quiz + questions in one
  transaction — nothing persisted unless generation fully succeeds (no orphaned empty
  quiz on failure). `documents.service.sample_subject_chunk_texts` (new) is a broad
  owner+subject chunk-*text* sample that selects only the `text` column (no embeddings
  loaded, no Cohere call) and evenly strides across the material for coverage — reuses
  existing retrieval, no re-embedding (per the pitfall). `delete_quiz` flushes question
  deletes before the parent (flush-before-parent rule — bit `delete_conversation`/
  `delete_document` before). Router: `POST` (201) / `GET` list / `GET` one / `DELETE` —
  thin, mirroring documents/ask. Exception→status: 404 unowned subject, 422 no material
  (`NoQuizMaterialError`), 502 generation failure. Wired into `app/main.py`.
- **Answer-key decision, documented in `schemas.py`**: this generation+review increment
  has no graded-submission flow, so the read shapes deliberately reveal
  `correct_index`/`explanation` (self-study tool, owner-scoped). A future graded flow
  must add a separate answer-hidden "take" shape and reveal only post-submission —
  documented so this is a deliberate choice, not an accidental answer-key leak.
  `owner_id` never exposed on any read shape.
- **`chore(frontend)`**: regenerated `schema.d.ts` (quiz route types now in the typed
  client; `tsc` clean, no consumer yet — the quiz UI is the next increment).
- Tests: `test_quiz_generation.py` (10, Anthropic client mocked directly, same pattern
  as test_llm/test_summarization — tool schema + forced tool_choice sent, tool_use
  parsed back, every malformed path → `QuizGenerationError`, empty-excerpts
  short-circuit without constructing a client, missing-key `RuntimeError`).
  `test_quiz.py` (19 SQLite integration + 1 live; generation mocked at the service
  boundary offline, chunks seeded directly since quiz gen only reads text): persist
  quiz+questions in order with no `owner_id` leak; 404 unowned/missing subject, 422 no
  material, 502 generation failure (and nothing persisted on failure); num_questions
  passthrough + bounds (0/21 → 422); list/get owner+subject scoping + cross-subject
  404s; delete removes quiz+questions, 404s for missing/another-owner/different-subject
  and leaves them intact. Backend **150 passed** (7 deselected live, up from 121/6),
  `ruff` clean.
- **Live-verified end-to-end** two ways: (1) the `-m live` quiz test — real Neon +
  Cohere + Claude tool-use, asserted well-formed questions (≥2 options, in-range
  `correct_index`), cleaned up. (2) The **full real stack** — real Inngest Dev Server +
  real R2/Neon/Cohere/Claude: real HTTP upload (auth dependency overridden, no Clerk JWT
  outside a browser) → `pending` → Inngest job → `ready` with summary in ~4s →
  `POST /quizzes` → 4 well-formed MCQs from real Claude tool-use, each with an in-range
  correct answer → `GET` re-fetched the persisted quiz, list returned the summary shape.
  Cleaned up via real `DELETE`s; Neon confirmed clean (0 rows across all five tables).
  Throwaway script, not committed. Not browser-tested (no browser/Clerk auth here) — the
  quiz frontend is the next increment.

## 2026-07-17 — Cohere Rerank in the Ask retrieval path (Phase 1 genuinely complete)
- `docs/plan.md`'s Phase 1 line is "Ask (retrieve → Cohere Rerank → Claude)" — vector
  search and Ask existed, but the Rerank step between them was never built. This was
  the last open Phase 1 item; Phase 2 (Quiz) starts next.
- **`feat(backend)`**: `documents/rerank.py` (new, beside `embedding.py` — same Cohere
  client concern): `rerank(query, texts, top_n) -> list[(index, relevance_score)]` via
  `rerank-v3.5` (Cohere's multilingual rerank model — an English-only one would
  degrade non-English subjects, same reasoning as `embed-multilingual-v3.0`). Reuses
  `embedding._get_client` directly rather than duplicating the `COHERE_API_KEY` check —
  one `Client` instance already supports both `.embed()` and `.rerank()`. Confirmed the
  real SDK signature/response shape (`co.rerank(model=, query=, documents=, top_n=)`,
  `.results[i].index`/`.relevance_score`) by introspecting the installed `cohere`
  package and a real one-off call before writing any code against it — the real call
  correctly ranked a photosynthesis sentence over an unrelated one (0.70 vs. 0.02).
  Any API/network failure → `RerankError`.
  - `documents/service.py`: `search_chunks` now retrieves a **wider** vector-similarity
    candidate pool (`RERANK_CANDIDATE_POOL = 30`, same owner/subject/embedding-NOT-NULL
    filters as before — widening only changes the `LIMIT`) on the Postgres path, then
    hands it to a new `_rerank_candidates(query, candidates, top_k)` helper, which
    reranks and cuts down to `top_k` — that's what actually reaches Claude, never the
    wider pool. `_rerank_candidates` is pure Python over an already-fetched list (no
    DB/dialect dependency), so it's directly unit-testable regardless of Postgres vs.
    SQLite. The SQLite branch (used by the whole offline test suite) is untouched —
    `<=>` is Postgres-only, so there's no vector ordering to rerank there in the first
    place, same as before this increment.
  - **Graceful degradation, decided and documented in `_rerank_candidates`'s
    docstring**: a `RerankError` must not break Ask, which already degrades
    gracefully everywhere (`ask/service.py`). On failure, falls back to the
    pre-rerank vector-similarity order truncated to `top_k` (not an error) — same
    best-effort spirit as `process_document`'s summary step. The returned
    `similarity_score` means Cohere's `relevance_score` on the reranked path, or raw
    cosine similarity on the fallback — documented on `ask/schemas.py`'s
    `SourceChunk.similarity_score` since both are "higher = more relevant" but not on
    the same scale.
  - `ask/service.py`/`prepare_ask_stream` needed **no changes** — both already call
    `search_chunks` as the shared entry point, confirmed by reading both call sites;
    the reranked/graceful-fallback behavior is transparent to them.
- Tests: `test_rerank.py` (new, 6 — Cohere client mocked directly, same pattern as
  `test_embedding.py`: empty-list short-circuit, call shape, index/score mapping,
  `top_n` capped at input length, API-failure wrapping, and one test proving the
  `COHERE_API_KEY` check is genuinely *reused* from `embedding.py` rather than
  duplicated — patches `rerank._get_client` back to the real
  `embedding._get_client` and confirms the same `RuntimeError`).
  `test_search.py` (+4, `_rerank_candidates` — pure logic, no DB: reorders by
  Cohere's relevance score, `top_k` respected, a forced `RerankError` falls back to
  the original vector order untouched, empty candidates short-circuit without
  calling rerank). Existing live semantic-ranking test extended in place (per the
  task's ask to extend rather than duplicate fixtures) —
  `test_search_chunks_orders_by_relevance_via_real_rerank` now exercises the full
  real retrieve→rerank pipeline, not just raw cosine order. Backend **121 passed**
  (6 deselected live, up from 112/6), `ruff check` clean.
- **Live-verified end-to-end** two ways: (1) `-m live` suite (6 passed, including the
  extended real-rerank test) — Neon confirmed clean afterward. (2) The full real
  pipeline: uploaded 4 real documents (2 on-topic photosynthesis docs, 2 off-topic)
  through the real service layer (real R2/Cohere), then hit the real
  `POST /subjects/{id}/ask` endpoint over real HTTP (auth dependency overridden — no
  real Clerk JWT outside a browser, same technique as prior live-HTTP scripts) —
  real Cohere Rerank scores clearly separated on-topic (0.75, 0.72) from off-topic
  (0.03, 0.02) chunks, and the answer was grounded with correct
  `(filename, chunk N)` citations from both on-topic documents. Cleaned up via real
  `DELETE` calls (documents, subject, conversation); Neon confirmed clean afterward.
  Throwaway script, not committed.
- `docs/PROGRESS.md`: Phase 1 is now genuinely complete — Rerank was the last item;
  the "Phase 1 complete" claim before the auto-summary increment was premature twice
  over. Phase 2 (Quiz) is next.

## 2026-07-17 — Auto-summary on document upload (Phase 1 gap closed)
- `docs/plan.md`'s Phase 1 ingest step was "chunk → Cohere embed → pgvector +
  auto-summary", but auto-summary was never actually built — `PROGRESS.md`'s "Phase 1
  complete" claim was wrong on this point. Closes that gap; adds it to the Inngest
  ingest job.
- **`feat(backend)`**: `Document.summary: str | None` (nullable — stays NULL for
  legacy rows, `failed` documents, and a `ready` document whose summarization step
  itself failed). Migration `35c81d01e21d_add_summary_column_to_documents`, applied to
  Neon, confirmed via `information_schema`.
  - `documents/summarization.py` (new, documents' own concern — not `ask/llm.py`):
    `summarize_document(text) -> str` via Claude (`claude-haiku-4-5-20251001`), same
    Anthropic SDK pattern as `ask/llm.py`. Multilingual: system prompt instructs
    "respond in the same language the excerpt itself is written in" (same approach as
    the Ask prompt). Input capped at `MAX_INPUT_CHARS` (12,000 chars) — summarizing a
    full 20 MB upload in one background-job step would be slow/expensive; the opening
    portion is representative enough for a short recall summary. Missing
    `ANTHROPIC_API_KEY` → bare `RuntimeError` at point of use (same deployment-mistake
    pattern as `db.py`/`embedding.py`/`ask/llm.py`); any Claude API/network failure →
    `SummarizationError`.
  - `service.process_document`: after a successful chunk+embed (`status: ready`),
    calls `summarize_document` and writes the result to `document.summary`. **Best-effort
    by design, unlike the parse/embed step it follows**: a `SummarizationError` is
    caught and logged, leaving `summary` NULL — the document still resolves to `ready`
    with its chunks/embeddings intact. A missing `ANTHROPIC_API_KEY` is *not* caught
    (same loud-failure reasoning as the missing-`COHERE_API_KEY` case above it) — an
    infra/deployment problem should fail the job and let Inngest retry, not silently
    masquerade as "no summary available".
  - `DocumentRead` gained `summary: str | None`.
- **`feat(frontend)`**: subject-detail page shows the summary as muted text under the
  filename/status/delete row, only when `status === "ready"` and a summary exists.
  `schema.d.ts` regenerated (`npm run generate-api-types`) — picked up the new
  `summary` field; fixed a stale test fixture in `documentsPolling.test.ts` that TS
  then correctly flagged as missing the new required field.
- Tests: offline (`test_summarization.py`, 4 — call shape/system prompt, input
  truncation at `MAX_INPUT_CHARS`, API failures wrapped as `SummarizationError`,
  missing-key `RuntimeError`; Anthropic client mocked directly, same pattern as
  `test_llm.py`). `test_documents.py` (+3, autouse `_mock_summarization` fixture so
  every existing `process_document` test gets a deterministic summary for free):
  a successful process writes the summary; a forced `SummarizationError` still
  resolves to `ready` with chunks intact and `summary` NULL; a parse failure also
  leaves `summary` NULL. Plus 1 live test (`-m live`) hitting real Claude, asserting a
  real non-empty summary comes back. Backend **112 passed** (6 deselected live, up
  from 105/5), `ruff check` clean. Frontend: `tsc`/`eslint` clean, `npm run build`
  succeeds, **51 passed** (14 files, unchanged count — no new pure helper, the display
  is a direct JSX conditional).
- **Live-verified end-to-end** three ways: (1) `-m live` suite (6 passed, incl. the
  new real-Claude summarization test) — Neon confirmed clean afterward (0 rows for the
  test owner across all three tables). (2) The full real pipeline: real HTTP upload
  against the real app (auth dependency overridden — no real Clerk JWT available
  outside a browser, same technique as prior live-HTTP scripts) + the real Inngest Dev
  Server + real R2/Cohere/Claude — `pending` immediately, resolved to `ready` in ~4s
  with a genuine Claude-generated summary populated, then cleaned up via real `DELETE`
  calls; Neon confirmed clean afterward. Throwaway script, not committed. Not
  click-tested in a real browser (no browser/Clerk auth available here) — same
  standing gap as every other frontend page in this project.
- `docs/PROGRESS.md`'s "Phase 1 — Core RAG: complete" line corrected: auto-summary was
  the missing piece, now shipped here. Cohere Rerank (search_chunks → Rerank → Claude
  in the Ask retrieval path) is the next increment, not yet started.

## 2026-07-17 — Frontend: delete-document button (closes out Phase 1 Core RAG)
- Wires a delete button into the subject-detail page for the `DELETE
  /subjects/{subject_id}/documents/{document_id}` endpoint added last increment —
  the last open Phase 1 item.
- First, cleaned up a stray uncommitted edit already in
  `subjects/[subjectId]/page.tsx` (`break-words` → `wrap-break-word`) that predated
  this work and wasn't part of it — discarded (`git checkout`) rather than folded
  in, since there was no evidence it was intended.
- `lib/api/schema.d.ts` regenerated against the running backend — the DELETE route
  (plus `/ask/stream` and `/api/inngest` from earlier increments) weren't in the
  typed client yet; confirmed `api.DELETE(...)` for the document path is now typed.
- **`feat(frontend)`**: destructive-variant icon button per row (`Trash2`,
  `window.confirm`, same pattern as the ask page's conversation-delete), a
  `useMutation` that checks `error` not `data` (204 leaves `data` undefined — not a
  failure), invalidates the documents query on success (same query key
  `documentsRefetchInterval` polls, unchanged). Per-row pending state so deleting one
  document doesn't disable every button. Deliberately not gated on document status —
  a still-`pending` document can be deleted too, matching what the backend allows.
  `lib/deleteError.ts` (`friendlyDeleteError`, 2 tests) maps 404 to a specific
  message, mirroring `friendlyUploadError`.
- Verified: `tsc --noEmit` clean, `eslint` clean, `npm run build` succeeds, **51
  passed** (14 files, up from 49/13). Not click-tested in a real browser — no
  browser/Clerk auth available in this environment; the backend endpoint itself was
  already live-verified end-to-end last increment, and this is a thin typed wrapper
  mirroring an already-proven pattern.
- Phase 1 Core RAG is now complete.

## 2026-07-17 — DELETE document endpoint (closes the R2 object-lifecycle gap)
- `DELETE /subjects/{subject_id}/documents/{document_id}` — removes a document's
  `DocumentChunk` rows, its R2 object, and the `Document` row. Files were never
  removed once uploaded before this.
- **`feat(backend)`**: `service.delete_document` (owner+subject scoped, same lookup
  as `get_document`) + a thin router DELETE (204, mirrors `ask.router`'s
  `delete_conversation` pattern: `if not service.delete_document(...): raise 404`).
  - Chunks deleted + flushed before the Document row (no ORM cascade in this
    codebase — same fix pattern as the Document/DocumentChunk and
    `delete_conversation` cleanups before it).
  - R2 delete happens *after* the DB delete commits, not before — avoids the DB
    row surviving a failed R2 delete (fine either way, idempotent) while avoiding
    the worse case: an R2 delete succeeding then the DB delete failing, which
    would leave a row pointing at a missing object. Once the DB row is gone,
    there's nothing left to "point at" anything, so the R2 delete afterward is
    best-effort — exceptions are caught/logged, not re-raised, so a transient R2
    failure can't turn an already-successful deletion into a 500. A `None`
    `r2_object_key` (legacy row) just skips the R2 step.
- Tests: chunks+object+row all removed; deleting a still-`pending` document (no
  chunks yet); 404s for missing document/subject/another-owner's-document (and
  confirmed untouched) /different-subject; tolerates a simulated R2 failure and a
  `None` key. Live test deletes a real document and confirms the object is
  actually gone from the real bucket — the offline R2 fake fixture now skips
  itself for `@pytest.mark.live` tests so this one hits real `r2_client`. **105
  passed** (5 deselected live), ruff clean.
- **Live-verified end-to-end** twice: the `-m live` suite (5 passed), and the
  full real HTTP flow (upload → real R2 → `DELETE` → 204 empty body → `GET` 404
  → confirmed gone from real R2 `NoSuchKey` → re-`DELETE` 404). Neon left clean.
  Throwaway script, not committed.
- Frontend not wired this increment (optional per the task, not half-wired) —
  noted as a follow-up in PROGRESS.md.

## 2026-07-17 — Cloudflare R2 file storage (replaces the raw_content stash)
- Uploaded files now persist to Cloudflare R2 (S3-compatible) instead of the interim
  `documents.raw_content` BYTEA column the Inngest increment added; that column is
  removed.
- **Precondition checked first**: `backend/.env` had no R2 creds — reported it as a
  blocker; the user added `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/
  `R2_BUCKET_NAME` (bucket var is `_NAME`, matched that), verified present, proceeded.
- **`feat(backend)`**: `app/core/r2_client.py` — one shared boto3 S3 client against
  the R2 endpoint (`https://<account_id>.r2.cloudflarestorage.com`), `put/get/delete_object`
  + owner-scoped `build_object_key` (`{owner_id}/{document_id}/{filename}`). Missing
  creds → `R2ConfigError` at point of use (lists which vars are missing). `boto3>=1.34`;
  Settings + `.env.example` updated.
  - `create_document` uploads to R2 *before* committing the pending row (failed upload
    → nothing persisted), after the 20 MB check (never upload-then-reject).
    `process_document` fetches bytes from R2. `models.py`: `r2_object_key` added,
    `raw_content` removed. Migration `4220579b8fb6`, applied to Neon.
  - Object kept after processing (R2 is the file store now). Idempotency intact —
    delete-then-reinsert still guards against duplicate chunks on a retry that
    re-fetches the same bytes. No delete-document endpoint yet, so no new orphan path
    (one object per document); a future endpoint should call `delete_object`.
  - Ownership verified at the DB layer before touching R2; keys are owner-prefixed so
    one owner's document_id can't resolve to another's object.
- Tests: `test_r2_client.py` (key builder, `R2ConfigError` per missing cred, boto3
  call args, + live real-bucket round-trip). Document/ask/search suites gained an
  in-memory R2 fake (autouse) so the default run stays offline. **97 passed** (4
  deselected live), ruff clean.
- **Live-verified end-to-end**: `-m live` (4 passed, incl. real-R2 round-trip); plus
  the full real pipeline (real Inngest Dev Server + real R2 + Neon/Cohere) — HTTP
  upload → file in real R2 immediately → `pending` → job fetched from real R2 →
  `ready` in ~1.5s, 1 chunk. R2 + Neon cleaned up (0 test objects left). Throwaway
  scripts, not committed.

## 2026-07-16 — Async document processing via Inngest
- Moved document processing (parse → chunk → Cohere embed → persist) off the
  request path into an Inngest background job. Upload returns `pending`
  immediately; the job resolves it to `ready`/`failed`.
- **Precondition checked first**: `backend/.env` had no `INNGEST_*` keys —
  reported it as a blocker and stopped; the user added `INNGEST_EVENT_KEY` +
  `INNGEST_SIGNING_KEY`, verified present (non-empty), then proceeded.
- **`feat(backend)`**: `inngest>=0.5`; `Settings.inngest_event_key/_signing_key`;
  `app/core/inngest_client.py` (one shared client + `require_event_key()` →
  RuntimeError at point of use if unset). `service.create_document` split into a
  sync path (validate + insert `pending`, return) and `process_document` (the
  job's parse/chunk/embed/persist work); `enqueue_document_processing` emits the
  `document/uploaded` event; `documents/jobs.py` is the thin Inngest function
  (wrapped in one `ctx.step.run` for retry durability); `main.py` serves it at
  `/api/inngest`.
  - Idempotent for retries: deletes prior-attempt chunks before re-inserting,
    no-ops once `raw_content` is cleared. Keeps the failed-parse/embed →
    `status: failed`, zero-chunks invariant; missing `COHERE_API_KEY` still
    raises loudly rather than marking the document failed.
  - **Migration despite the task's "likely none"**: the job runs in a separate
    request (Inngest calls back over HTTP), so it needs the file bytes from a
    shared store — but the file isn't persisted yet (R2 is next) and an event
    can't carry a 20 MB PDF. Added a temporary nullable `documents.raw_content`
    (BYTEA) column that stashes the bytes until the job consumes them, then
    clears to NULL. Migration `7877073ae76d`, applied to Neon. R2 replaces it later.
- **`feat(frontend)`**: subject-detail page polls the documents list while any
  document is `pending` (`lib/documentsPolling.ts` → TanStack Query
  `refetchInterval`), stopping once all settle. Upload copy updated. Chose to add
  polling here, not defer — otherwise the async change would leave documents
  stuck on `pending` in the UI with no refresh.
- Tests: `test_documents.py` restructured (upload → pending + enqueued + nothing
  processed on-request; parse/chunk/embed moved to direct `process_document`
  tests; idempotency: retry-after-success no-op, retry-after-partial
  delete-then-reinsert; missing-doc no-op). `test_inngest.py` (new: missing-key
  RuntimeError + event-send shape). `test_ask.py`/`test_search.py` process the
  document after create so their live tests still have chunks. Backend **89
  passed** (3 deselected live), ruff clean. Frontend `documentsPolling.test.ts`
  (4); **49 passed** (13 files), tsc/eslint clean.
- **Live-verified end-to-end** with the real Inngest Dev Server
  (`npx inngest-cli dev`) + real Neon + real Cohere: uploaded a doc through the
  real HTTP API → `pending` immediately → the job resolved it to `ready` in ~3s
  with 1 chunk persisted. Plus `-m live` suite (3 passed). Neon left clean.
  Throwaway scripts, not committed. Not browser-tested with real Clerk auth —
  the poll/badge UX wants a manual pass.

## 2026-07-16 — Ask endpoint streaming (SSE), backend + frontend
- Converts the Ask endpoint to SSE — explicitly deferred twice before this
  (see PROGRESS.md). Non-stream `POST /subjects/{subject_id}/ask` kept as-is;
  new `POST .../ask/stream` added alongside it.
- **`feat(backend)`**: `llm.ask_claude_stream` (shares message-building with
  `ask_claude` via a new `_build_messages` helper, so prompt/citation contract
  can't drift between the two), `service.prepare_ask_stream` +
  `service.stream_answer`, `POST /subjects/{subject_id}/ask/stream`.
  - Split into `prepare_ask_stream`/`stream_answer` because a
    `StreamingResponse`'s status is locked in once its body starts iterating —
    404s (`SubjectNotFoundError`/`ConversationNotFoundError`) have to come from
    an ordinary call the router can still catch normally, not from inside the
    generator.
  - Event shape: `event: token` / `data: {"text"}` deltas, one terminal
    `event: done` / `data: {"conversation_id", "turn_id", "sources"}`.
  - Turn persisted exactly once, as the literal last statement in
    `stream_answer`, after the token loop fully resolves (success, no-material,
    or a caught `LLMError`) — never per-delta, never with partial text. A
    mid-stream `LLMError` after some real deltas already went out keeps that
    partial text as the answer (with its sources) instead of appending a
    "try again" message after genuine grounded output.
  - Client-abort decision (documented in `stream_answer`'s docstring, since the
    task called this out explicitly): the generator is torn down before ever
    reaching the persistence step if the client disconnects mid-stream — no
    half-written turn is structurally possible, since persistence only ever
    runs with the complete answer. If the client just navigates away without a
    clean disconnect, generation keeps running server-side and still saves —
    matches how Claude.ai/ChatGPT's own chat UIs behave.
  - Tests: `test_llm.py` (+4, incl. that the missing-key `RuntimeError` only
    surfaces on first iteration — a generator function's body doesn't run at
    call time). `test_ask.py` (+9, mirroring the non-stream suite one-for-one,
    plus 1 live end-to-end test against real Neon+Cohere+Claude). Backend: 83
    passed (26 new), `ruff check` clean.
  - **Live-verified** (pytest live test, service-layer — same reasoning as
    every other live test here, no real Clerk JWT outside a browser): real
    tokens streamed in, `done`'s sources were non-empty and grounded, the
    persisted turn's answer matched the streamed text exactly.
- **`feat(frontend)`**: `lib/parseSSE.ts` (`createSSEParser`) — the one
  genuinely pure piece of this, an incremental parser buffering a partial
  SSE event/line across arbitrary `ReadableStream` chunk boundaries; 6 tests,
  including one event deliberately split across three chunks.
  `lib/api/streamAsk.ts` drives the actual request: `EventSource` can't attach
  the Clerk bearer token (GET-only, no custom headers), so this is `fetch()` +
  a manual `ReadableStream` reader, attaching the token the same way
  `useApiClient`'s middleware does.
  - `ask/page.tsx`: `askQuestion` mutation replaced with `startAsk` (drives
    `streamAsk`); the old `pendingQuestion` string became a `streaming
    { question, answer }` object driving both the pending question bubble and
    a new live-filling `AnswerMessage` (new `streaming` prop, hides
    copy/pin/read-aloud on not-yet-complete text). Edit/resend still goes
    through `splitTurnsAtEdit` with the same restore-on-failure behavior as
    before. Added an `AbortController` per stream — aborted on unmount and on
    switching/starting a conversation mid-stream (the server keeps generating
    and persisting regardless; this only stops updating a component that's
    moved on). Editing a different turn while one is already streaming is now
    a no-op instead of allowing two concurrent asks.
  - `react-markdown` stayed without `rehype-raw` — no new HTML-injection
    surface from rendering partial/streamed markdown.
  - Frontend: `tsc --noEmit` clean, `eslint` clean, 45 passed (13 files, up
    from 37/11).
- **HTTP-level live verification** (added after the commits below, since
  TestClient buffers the SSE body and can't prove incremental delivery): ran
  the real app under `uvicorn` on a real socket with the Clerk auth dependency
  overridden (no real JWT here; Neon/Cohere/Claude all real), hit `/ask/stream`
  with an `httpx` streaming client, and timestamped each raw wire chunk — 3
  chunks arrived spread over 0.72s, confirming genuine incremental delivery off
  the socket (not a buffered blob). Answer grounded with an inline citation, one
  source in `done`, Neon left clean. Throwaway script, not committed. Also
  re-ran `pytest -m live tests/test_ask.py` (2 passed) and confirmed Neon clean.
- **Still not done**: real browser click-through with live Clerk auth (React-UI
  token rendering, edit-resend over the stream, mid-stream conversation switch)
  — no browser in this environment; the transport layer under all of it is now
  verified, only the React wiring is unproven. A pre-existing local
  `uvicorn --reload` dev server was found serving stale code (missing the new
  route); needs a manual restart before that browser pass.
- Commits: `ee23fef` (backend SSE), `04f7ea6` (frontend streaming),
  `a59ee9e` (docs) — all on `develop`, pushed to `origin/develop`.

## 2026-07-16 — Frontend: Ask/RAG chat UI + conversations list, responsive/color pass
- Closes the last open Phase 1 frontend page: `/subjects/[subjectId]/ask`. Backend
  (Ask endpoint + Conversations CRUD) already existed from earlier increments.
- **`docs(frontend)`**: `docs/FRONTEND.md` (new) — mobile-first responsive rules and
  semantic-color-token rules for every page/component; CLAUDE.md rule 7 added
  requiring it. Then applied retroactively to the pages that predate the rule:
  `globals.css`'s `--primary`/`--ring` moved from grayscale to an indigo/blue OKLCH
  value (light + dark); home, `/subjects`, `/subjects/[subjectId]`, sign-in, sign-up
  moved to `p-4 sm:p-8`; subject detail page's title and filename rows now wrap/
  truncate instead of overflowing at narrow widths.
- **`feat(frontend)`**: the ask page itself.
  - Sidebar: new-conversation button, conversations grouped by date
    (`lib/groupConversationsByDate.ts`), filtered from the owner-wide `GET
    /conversations` down to this subject (`lib/conversationFilter.ts`), each item
    previewing its first question (`lib/truncateText.ts`) — fetched up front for
    every listed conversation via `useQueries` (not just the active one), so
    previews are real and opening one is instant.
  - `components/question-message.tsx` / `answer-message.tsx`: question bubbles
    (copy/edit/delete) and answer bubbles (markdown via `react-markdown`, copy/pin/
    read-aloud via `speechSynthesis`, citations simplified with
    `lib/simplifyCitations.ts` to drop the `chunk N` suffix but keep the filename).
  - Edit & resend ("regenerate from here" — the backend has no per-turn edit, only
    whole-conversation CRUD): drops the edited turn and everything after it from
    the visible transcript, resends with the same `conversation_id`.
  - Added `@testing-library/user-event` (dev dep) and `react-markdown` (dep).
    `vitest.setup.ts` gained an explicit `afterEach(cleanup)` — without it, DOM
    from earlier tests in the same file stuck around once tests started using
    `user-event` across multiple `it()`s in one file, causing "multiple elements
    found" failures in later ones.
  - Tests: `conversationFilter.test.ts`, `groupConversationsByDate.test.ts`,
    `relativeTime.test.ts`, `simplifyCitations.test.ts`, `truncateText.test.ts`,
    `question-message.test.tsx`, `answer-message.test.tsx`. No page-level test —
    matches this codebase's existing pattern (pure helpers/components tested,
    pages verified live), see the fixes below for why that pattern has a real gap.
- **Four real UX bugs, all found by the user live-testing the pending/edit flow in
  the browser** (not caught by any test beforehand — page-level interaction bugs,
  not pure-logic ones):
  1. A failed edit-resend permanently dropped the question — it had already been
     spliced out of the transcript before the request even completed, and nothing
     put it back on error. Fixed by holding the removed turns in a ref and
     restoring them in the mutation's `onError`.
  2. The finished turn and the still-visible "Sending…" placeholder bubble could
     both be on screen for one render — `pendingQuestion` was cleared in a
     separate `onSettled`, not atomically with the turn update. Fixed by clearing
     it directly inside `onSuccess`/`onError` instead.
  3. The compose box kept showing the just-submitted text (only cleared in
     `onSuccess`) while the pending bubble below showed the same text — looked
     like the question was shown twice. Fixed by clearing the box on submit, and
     restoring the text into it on error (only for a plain new question, not an
     edit-resend, where the restored turn card already covers that).
  4. Following fix 3, the emptied box's default placeholder made the pending
     state look like a reset/error rather than "in progress". Landed on hiding the
     compose form entirely while a request is in flight (matching Claude's own
     chat input), rather than a pending-specific placeholder — user's call after
     an intermediate placeholder-text attempt didn't read right either.
  - **`refactor(frontend)`**: extracted the one piece of bug #1 that's pure logic
    — the turns-array split at the edited turn — into `lib/editTurn.ts`
    (`splitTurnsAtEdit`), with 5 tests (split at start/middle/end, turnId not
    found, empty transcript). This is now the only page-adjacent logic from this
    increment that has direct test coverage; the rest of the fixes above were
    verified live in the browser only.
  - Action-row layout in both message components changed too, per user feedback
    during the same testing pass: icon buttons + timestamp moved from a single
    left-aligned row to right-aligned, timestamp stacked above the buttons.
- Verified: `npx tsc --noEmit` clean, `npm run lint` clean, `npm run test` →
  **37 passed** (11 files, up from 8).

## 2026-07-16 — Frontend: Vitest test suite + review fixes from Subject detail page
- An overseer review of commit `c5474ec` (Subject detail page + upload) flagged
  one real deviation from CLAUDE.md rule 4 ("every change ships with a test") —
  the frontend had zero automated tests across both increments so far
  (`75c58f9`, `c5474ec`), shipped on manual `tsc`/`eslint`/browser checks only —
  plus a few minor nits in the same file. Fixed both, split into two commits.
- **`test(frontend)` — `c292ea5`**: bootstrapped Vitest.
  - `npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react
    @testing-library/jest-dom` initially failed: the latest `@vitejs/plugin-react`
    (6.x) pulls in `@rolldown/plugin-babel`, which peer-depends on a Babel 8
    release candidate — conflicting with `shadcn`'s Babel 7 dependency tree.
    Pinned `@vitejs/plugin-react@^4` (landed on 4.7.0) instead, which installed
    cleanly with no `--legacy-peer-deps` hack needed.
  - `vitest.config.ts`: `environment: "jsdom"`, `@vitejs/plugin-react`, and a
    `resolve.alias` mapping `"@"` → `./src` — without this, every test importing
    `@/components/...` or `@/lib/...` (which is all of them, matching the app's
    own import style) would fail to resolve.
  - `vitest.setup.ts` imports `@testing-library/jest-dom/vitest` specifically,
    not the bare `@testing-library/jest-dom` package root. First attempt used the
    bare import and every test file failed immediately with `ReferenceError:
    expect is not defined` — traced to jest-dom's default entry point assuming a
    Jest-style global `expect`, which Vitest doesn't inject unless
    `test.globals: true` is set. The package ships a dedicated
    `@testing-library/jest-dom/vitest` entry that calls `expect.extend` using
    Vitest's own `expect` import instead; switching to it fixed all three
    suites immediately.
  - `package.json`: `"test": "vitest run"`, `"test:watch": "vitest"`.
  - Extracted the Subject-detail page's two pure helpers so they're testable in
    isolation, per the task's design: `friendlyUploadError(status)` →
    `lib/uploadError.ts`, and the inline `document.status === "ready" ? ... :
    ...` ternary → `documentStatusVariant(status)` in `lib/documentStatus.ts`
    (typed against the generated `components["schemas"]["DocumentStatus"]` union
    and the `Badge` component's own `VariantProps`, so it can't drift from either
    without a type error).
  - Tests (8, all passing): `uploadError.test.ts` (415/413/other-status
    branches), `documentStatus.test.ts` (ready/failed/pending), and a
    `Badge` render smoke test (`badge.test.tsx`) — deliberately chosen as the
    first component test since `Badge` needs no providers (no Clerk/Router/
    QueryClient), proving the component-testing setup itself works correctly
    before any future page needs heavier test scaffolding.
  - To land this as a clean, reviewable "test" commit separate from the "fix"
    commit below (same file, same review), staged an intermediate version of
    `page.tsx` with *only* the extraction change (swap the two inline helpers
    for imports) — none of the nit fixes yet — verified it independently
    (`tsc`/`eslint`/`vitest` all clean), committed and pushed that first, then
    layered the nit fixes on top as their own commit.
- **`fix(frontend)` — `846fd1d`**: the three minor nits.
  - `onError` on the upload mutation now resets the file input too (previously
    only `onSuccess` did) — without this, retrying the exact same file after a
    transient failure silently did nothing, since browsers don't re-fire
    `onChange` when the input's value hasn't actually changed.
  - Renamed the documents `.map()` callback param `document` → `doc` — it was
    shadowing the global `document` object (harmless today since nothing in that
    closure touches the real DOM `document`, but worth not leaving as a latent
    footgun).
  - When `subjectQuery.isError` (the subject doesn't exist or isn't owned by the
    caller — the backend already enforces this), the page now shows "Subject not
    found" and returns early, instead of still rendering the upload card and an
    empty documents list underneath a broken header. Extracted the back-link
    into a small `backLink` local so both the error and normal render paths
    share it rather than duplicating the JSX.
- Verified before each commit: `npx tsc --noEmit` clean, `npm run lint` clean
  (confirmed via `eslint --format json` that the new test/config files were
  actually linted, not silently skipped by an ignore pattern), `npm run test` →
  **8 passed** both times (the intermediate extraction-only state and the final
  state).

## 2026-07-16 — Frontend: Subject detail page (documents list + upload)
- New route `app/subjects/[subjectId]/page.tsx`, second frontend increment (after
  `/subjects` list+create). Client component (matches `/subjects`'s existing
  pattern), reads the dynamic segment via `useParams()` rather than splitting into
  a server-component wrapper just to get typed `params` — not worth the extra
  indirection for a single string param. `GET /subjects/{subject_id}` (name) and
  `GET /subjects/{subject_id}/documents` (list), both already-existing backend
  endpoints, both via the typed client + React Query — no backend changes this
  increment.
- Upload: shadcn `Input` with `type="file"` drives a `useMutation` that builds a
  real `FormData` and calls `POST /subjects/{subject_id}/documents`. Before
  writing this, read `openapi-fetch`'s source (`node_modules/openapi-fetch/dist/
  index.mjs`) rather than guessing how it handles multipart: confirmed
  `defaultBodySerializer` special-cases `body instanceof FormData` and returns it
  untouched (skipping `JSON.stringify`), and that it deliberately omits a
  `Content-Type` header in that case so the browser can set the multipart boundary
  itself. The generated request-body type is `{ file: string }` (
  `openapi-typescript` has no way to render OpenAPI's `format: binary` as
  `File`/`Blob`, only `string`) — this is a known upstream limitation, not
  something to fix here, so the real `FormData` is cast to that type when passed
  as `body`. On success, invalidates the `["subjects", subjectId, "documents"]`
  query so the list refreshes without a manual refetch.
- Upload UX: `isPending` disables the file input and shows a "processing…" note
  (uploads are still fully synchronous — parse → chunk → real Cohere embed calls —
  so a multi-second wait is expected until Inngest exists). Errors read the
  **actual response status** (`response.status` off `openapi-fetch`'s return
  value) rather than trusting the generated `error` type — the OpenAPI schema only
  documents 201/422 for this route (FastAPI doesn't auto-document hand-raised
  `HTTPException`s unless you declare `responses={}`), so 404/415/413 exist at
  runtime but aren't in the generated types. Mapped 415 → "unsupported file type,
  use PDF/DOCX/TXT", 413 → "too large, 20 MB limit" (both messages matched to the
  backend's real `SUPPORTED_CONTENT_TYPES`/`MAX_UPLOAD_SIZE_BYTES`, read from
  `documents/parsing.py`/`service.py` rather than guessed), anything else → a
  generic retry message.
- Each document row: filename + a status `Badge` (added via `npx shadcn add
  badge`, the same Base-UI-variant component style as the existing
  button/card/input/label) — `default` for `ready`, `destructive` for `failed`,
  `secondary` for `pending`.
- `/subjects/page.tsx`: wrapped each subject `Card` in a `next/link` to its detail
  page. No middleware change needed — `/subjects(.*)` already matches the new
  nested route.
- Regenerated `lib/api/schema.d.ts` against the live backend before starting
  (`npm run generate-api-types`) to make sure the typed client reflected current
  reality rather than assuming the documents endpoints were still shaped the same
  as when the schema was last generated; diffed as unchanged, confirming they
  were.
- Tests/verification: `tsc --noEmit` clean; `eslint` caught one real issue (unused
  `Button` import left over from an earlier draft) before commit, fixed. No new
  backend tests — both endpoints hit here (`GET`/`POST .../documents`) were
  already covered by `tests/test_documents.py`.
- **User confirmed live in the browser**: opened a subject, uploaded a file, saw
  it reach `status: ready`. Went one step further before calling this done — the
  task explicitly asked to confirm chunks/embeddings actually get created, not
  just that the status flips — so queried Neon directly afterward (service layer,
  same reasoning as every other live check this project does: a real Clerk JWT
  would need scripting a browser session) and confirmed the uploaded PDF produced
  **34 real `DocumentChunk` rows, each with a genuine 1024-dim Cohere embedding**,
  not just a document row that happened to say `ready`.
- Also fixed `docs/PROGRESS.md`'s stale "Phase 0 — Setup: complete. Next up: Phase
  1" header — Phase 1 has been underway for many increments now (Subjects,
  Documents, Ask, Conversations, and two frontend increments all shipped under
  it); it now reads "Phase 1 — Core RAG: in progress" with a one-line summary of
  what's done vs. still open.

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
