# StudyMate — plan (condensed)

Full design & rationale live in the approved plan; this is the repo-local summary for continuity.

## Goal
Portfolio + learning Python. Education RAG SaaS for global (multilingual) students.

## Stack
| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLModel · Alembic |
| DB | Neon Postgres + pgvector (MVP: pgvector-only; FTS hybrid → Phase 2) |
| Auth | Clerk (JWKS verification in FastAPI) |
| Jobs | Inngest |
| Files | Cloudflare R2 |
| AI | Claude (Haiku 4.5 / Sonnet 5) generation + Cohere multilingual embeddings + Cohere Rerank |
| Billing | Polar (Merchant of Record) |
| Frontend | Next.js 15 (App Router) · React 19 · TS · Tailwind + shadcn/ui · TanStack Query · next-intl |

## Core features
Subjects · Upload (+ auto-summary) · Ask (cited RAG Q&A) · Quiz (structured) ·
Flashcards + SM-2 · Progress · Freemium (Free / Pro / Business-B2B).

## Roadmap
- **Phase 0** — Setup: monorepo, Neon + Clerk, SQLModel + Alembic, CI, continuity docs.
- **Phase 1** — Core RAG: Subjects, upload → R2 → Inngest ingest (chunk → Cohere embed →
  pgvector + auto-summary), Ask (retrieve → Cohere Rerank → Claude, streaming), Conversations.
- **Phase 2** — Quiz (structured JSON) + FTS hybrid (RRF).
- **Phase 3** — Flashcards + SM-2 SRS.
- **Phase 4** — Progress + Polar billing + Referral + Support/FAQ + Sentry/PostHog.
- **Phase 5** — Business/Teams (B2B): org, teacher assigns + tracks students, admin.
- **Phase 6** — Research mode (agentic, Tavily).
- **Phase 7** — Telegram + OCR (in progress): Telegram bot + image-upload OCR (Claude vision).
- **Phase 8** (deferred — revisit later) — mobile app (PWA or native).

## Conventions
Service layer · tenant scoping · tests per change · Conventional Commits · main/develop ·
DRY/SOLID/KISS/YAGNI. See `CLAUDE.md`.
