# Decisions (ADR log)

Short records of key choices and *why*. Add an entry when a core decision changes.

## 1. Language: Python (not full-stack TypeScript)
Goal is portfolio + learning Python; RAG's ecosystem is strongest in Python. Frontend stays
TypeScript (Next.js). Inspired by, but not copied from, the Lexara project.

## 2. Auth: Clerk (managed), not hand-rolled JWT
Eliminates the auth-bug class found reviewing Lexara (no rate-limit, reset-token leak,
fail-open webhook). FastAPI verifies Clerk session JWT via **JWKS**.

## 3. ORM: SQLModel + Alembic
Less boilerplate than raw SQLAlchemy, Pydantic-integrated, beginner-friendly.

## 4. DB + vector: Neon Postgres + pgvector
Single DB, serverless with branching. MVP = pgvector-only; Postgres FTS hybrid (RRF) added
in Phase 2 (avoids Lexara's per-query in-memory BM25 rebuild).

## 5. AI: Claude generation + Cohere multilingual embeddings
Claude (Haiku 4.5 default, Sonnet 5 for hard tasks); Cohere embeds Korean/English/Uzbek/…
Quiz/flashcard JSON via tool-use structured output (not fragile `json.loads`).

## 6. Frontend: Next.js 15 (App Router) — no tRPC
tRPC needs a TS backend; ours is Python. Type-safety via FastAPI OpenAPI → `openapi-typescript`.

## 7. Billing: Polar (Merchant of Record)
Handles tax/VAT globally; sandbox for dev. Tiers: Free / Pro / Business (B2B teams).

Settled while wiring it up (2026-07-17):
- **Polar's only job is to upsert one `UserPlan` row.** The entitlement layer (`LIMITS`,
  `ensure_can_*`, usage counts) stays provider-agnostic and knows nothing about it, so
  swapping providers touches the webhook and nothing else.
- **Products must be RECURRING**, not one-time. A one-time product emits `order.paid` and
  never any `subscription.*` event, so plans would never change — and nothing would ever
  expire, making a one-off payment buy a permanent plan.
- **Product → plan maps by product id** (env config), never by product name: names are
  mutable dashboard labels, ids are stable.
- **Free is never sold.** Free is the absence of a paid plan, so there is no Free product
  and checkout rejects it.
- **Downgrade on `subscription.revoked`, never `subscription.canceled`.** Canceled means
  "scheduled to cancel, access continues to period end"; revoked means access is gone.
- **No plan-change endpoint, ever.** A self-serve "set my own plan" route is an
  entitlement bypass; only a paid checkout + verified webhook may move a plan.

## 8. Observability: Sentry (errors) + PostHog (product analytics)
Sentry for unhandled exceptions (backend + frontend); PostHog for a small, deliberate
set of product events (frontend). Both optional/env-gated — same pattern as every
other third-party key in this codebase (Cohere/Anthropic/R2/Polar): unset means the
integration is simply off, never a startup failure.

- **PII policy**: only the Clerk user id is ever attached to error/event context —
  never email or name. Sentry's `sendDefaultPii` stays `false` (its own default,
  kept explicit); PostHog identifies by user id via `posthog.identify(id)`, reset on
  sign-out. No autocapture on either side — PostHog's DOM-click autocapture is
  explicitly disabled (`autocapture: false`); only 6 named events are ever sent
  (`subject_created`, `document_uploaded`, `quiz_generated`, `flashcards_generated`,
  `question_asked`, `checkout_started`, see `frontend/src/lib/analytics.ts`).
  Do-Not-Track is respected (`respect_dnt: true`).
- **`PlanLimitExceededError` is filtered out of Sentry** — it's an expected 402
  (billing.md's own app-wide handler), not an error worth alerting on. Filtered via
  `before_send`, generically (by exception type, passed in from `main.py`) rather than
  `app/core/sentry.py` importing a specific domain exception — keeps `app/core` free
  of a dependency on `app/modules`.
- **Backend init lives in a FastAPI `lifespan` hook, not module-level code.**
  `sentry_sdk.init()` globally patches process-wide machinery (the exception
  middleware class, `sys.excepthook`), so it must fire exactly once per real process,
  and normally that means calling it before the app is created. But this repo's tests
  build `TestClient(app)` without the `with TestClient(app) as client:` form, which
  means the ASGI lifespan protocol never runs during `pytest` — so module-level init
  would ALSO silently fire on every offline test run the moment a real `SENTRY_DSN`
  exists in `.env`, shipping test-generated exceptions to a real Sentry project. A
  lifespan hook only runs when something actually drives the lifespan (real `uvicorn`
  serving does; this repo's plain `TestClient(app)` does not) — discovered when a
  first pass at module-level init made a full `pytest` run try to flush real events on
  exit, once a real DSN had been added to `.env`.
- **One DSN for client + server + edge (`NEXT_PUBLIC_SENTRY_DSN`)**: a Sentry DSN is
  not a secret — the same value already ships inside the client JS bundle — so there's
  no reason to keep a separate server-only var. Simpler than most examples in Sentry's
  own docs, deliberately.
- **PostHog frontend-only.** A server-side PostHog client was in scope only "if
  clearly worth it" — every one of the 6 events already fires from a place with a
  Clerk-authenticated browser session, so a backend capture path would just duplicate
  the same signal through a second SDK for no new information. Skipped.

## 9. Teams/Orgs (Phase 5): Clerk Organizations, not custom DB tables
Organizations, memberships, roles, and invitations are backed by **Clerk Organizations**
(Clerk's native feature) — StudyMate builds **no** org/membership/invite tables of its
own. Clerk owns that data; our backend reads the *active organization* out of the same
Clerk session JWT it already verifies for auth (`app/core/auth.py` JWKS path), and the
frontend mounts Clerk's own org UI (`<OrganizationSwitcher/>`, `<OrganizationProfile/>`,
`<CreateOrganization/>`). Chosen because it eliminates a whole class of B2B auth work
(invite tokens, seat management, role storage, membership races) — the same "don't
hand-roll auth" reasoning as ADR #2 (Clerk over hand-rolled JWT).

- **Reading org context**: `app/core/org.py::extract_org_context(claims)` pulls the
  active org id/role out of an already-verified claim dict, handling **both** Clerk
  session-token shapes — v1 flat (`org_id`/`org_role`, present only with an active org)
  and v2 nested (`"v":2` → `o.id`/`o.rol`). No active org (personal workspace, or
  Organizations disabled on the instance) → `OrgContext(None, None)`, a valid state, not
  an error/401. `get_org_context` / `require_teacher` (FastAPI deps in `auth.py`) reuse
  the existing JWKS verification — no second verification path, no unverified token.
- **Role mapping**: Clerk's default org roles are `org:admin` / `org:member` (verified
  against the installed `@clerk/*` SDK type docs). We map **admin → `teacher`, member →
  `student`** (a custom `org:teacher` role is also honored if the instance ever adds
  one). Mirrored client-side in `frontend/src/lib/orgRole.ts` so UI and API authorize on
  the same role keys and can't drift. `student` is the safe default (teacher is the
  privileged capability).
- **Scope of increment 1 = foundation only**: create org / add-invite members / roles /
  see membership, via Clerk's UI + the backend org-context deps. **No content is
  org-scoped yet** — existing subjects/documents/quiz/flashcards stay `owner_id`-scoped
  unchanged; `require_teacher` guards nothing yet. Content org-scoping, teacher
  assign/track, and admin/billing seats are later Phase 5 increments.
