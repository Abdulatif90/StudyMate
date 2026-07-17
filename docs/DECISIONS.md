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
