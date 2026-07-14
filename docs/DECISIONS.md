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
