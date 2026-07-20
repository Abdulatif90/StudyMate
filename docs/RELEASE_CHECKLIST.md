# RELEASE CHECKLIST — StudyMate end-of-project pass

Single consolidated list of every step that was **deliberately deferred** during the build
(per the standing preference: defer live/browser/key work to one end-of-project pass rather
than blocking each increment). Each item is scattered across `docs/PROGRESS.md` /
`docs/WORKLOG.md`; this doc gathers, groups, and de-duplicates them into actions **you**
(the developer, with real accounts + a browser) can execute. Nothing here blocks the
automated test suites — those are all green (see "Automated verification" at the bottom).

Work top to bottom; A is the only one that will actually break a feature in production.

---

## A. Database — apply the one pending migration to Neon

The automated `alembic` check shows Neon is **one migration behind `head`**:

- `alembic heads` → `c1d2e3f4a5b6` (adds `telegram_links.active_subject_id`)
- `alembic current` (Neon) → `06650625fb97`

`c1d2e3f4a5b6` backs the new **Telegram "answer over your own materials"** feature; until
it is applied, that feature will error against Neon (the column doesn't exist yet). All
earlier migrations are already applied.

**Action** (from `backend/`, with `DATABASE_URL` pointed at the target Neon branch):

```bash
alembic current          # confirm 06650625fb97
alembic upgrade head     # applies c1d2e3f4a5b6
alembic current          # confirm c1d2e3f4a5b6
```

> The build intentionally never ran migrations against Neon; this is the batched apply.

---

## B. Live webhook / bot registration

### B1. Telegram webhook (bot: `@helperstudymatebot`)
The bot code is done end-to-end but the webhook is **not registered with Telegram** and the
verification secret is unset (while unset, the endpoint processes updates *unverified* —
dev-only).

**Action:**
1. Expose `POST /telegram/webhook` on a public HTTPS URL (ngrok for a test, or the real
   deploy URL).
2. Choose a strong secret and set it in `backend/.env`:
   `TELEGRAM_WEBHOOK_SECRET=<secret>` (and restart the backend).
3. Register the webhook with Telegram, passing the **same** secret as `secret_token`:
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
     -d "url=https://<public-host>/telegram/webhook" \
     -d "secret_token=<secret>"
   ```
4. Verify: DM the bot from a linked account, confirm `/subjects`, `/subject <n>`, a
   question answered from your own materials, and `/research <q>` all work.

### B2. Polar billing webhook → production
Polar is **sandbox-only** so far. The sandbox webhook was already live-verified (real
delivery flipped a plan Free→Pro). Going live is a separate environment.

**Action:**
1. In `backend/.env`: `POLAR_SERVER=production`, a **production** org access token,
   **production** product ids (Pro / Business), and the **production** webhook secret
   (`POLAR_WEBHOOK_SECRET`). Production has its own dashboard/products/tokens.
2. Register the production webhook endpoint at `POST /billing/webhook` in the Polar
   production dashboard, subscribed to `subscription.*` events.
3. Run one real production checkout and confirm the `UserPlan` row flips.

---

## C. Environment / secrets still needed

### C1. `CLERK_SECRET_KEY` — assignment roster
The teacher assignment **roster** (who has / hasn't submitted) enumerates an org's members
via the Clerk backend API, which needs a **secret** key (JWT verification alone can't list
members). Without it the roster endpoint returns a clean `503` and the UI shows "Roster
unavailable" — it does not crash.

**Action:** add `CLERK_SECRET_KEY=<sk_...>` to `backend/.env` in whatever environment goes
live, then confirm `GET /assignments/{id}/roster` returns real members.

### C2. Confirm all other keys per environment
Neon, Clerk (frontend + backend), Cohere, Anthropic, Inngest, R2, and Polar keys are in the
dev `backend/.env` / `frontend/.env`. For a real deploy, set each in that environment's
secret store. (All are env-gated: unset means the integration is simply off, never a
startup crash — but several features need them to function.)

---

## D. Observability — deliberately exercise live capture

The env-config bugs were already fixed (PostHog host, `NEXT_PUBLIC_SENTRY_DSN` naming). What
remains is a **one-time deliberate confirmation** that events actually land:

**Action:**
1. Trigger one intentional backend exception (a throwaway route or a forced error) and
   confirm it appears in the **Sentry** project. Confirm a frontend error appears too.
2. Perform one tracked product action (e.g. create a subject) and confirm the event
   (`subject_created`) appears in **PostHog**.
3. Confirm `PlanLimitExceededError` (expected 402) is **filtered out** of Sentry as designed.

---

## E. Batched manual browser click-through (real Clerk auth)

No browser was available during the build, so **every** frontend page shipped on
`tsc`/`eslint`/vitest + backend live-verification, with the in-browser pass deferred to
here (the standing "not browser-verified" gap noted throughout PROGRESS.md). Do one
sign-in and walk the app at **360px / 768px / 1280px** (per `docs/FRONTEND.md`), light + dark.

Cover at least:
- **Auth + shell**: sign-in/up, `AppShell` sidebar (desktop) + mobile top-bar menu, theme
  toggle persists, language switcher (en/uz/ko/ru) round-trips.
- **Subjects + documents**: create a subject; upload a **PDF**, a **DOCX**, a **TXT**, an
  **image** (photo of notes), and a **scanned/text-less PDF** — confirm the new accept-types
  hint shows, the picker now allows images, and each document polls `pending → ready`
  (or `failed`) on its own. Confirm the image and scanned PDF produce chunks (OCR worked).
- **Ask/RAG**: streaming answer token-by-token, sources, edit-and-resend, switching
  conversations mid-stream aborts the view while the turn still persists.
- **Quiz / Flashcards**: generate + take a quiz; run an SM-2 flashcard review session.
- **Progress + dashboard**: per-subject and overall.
- **Billing**: `/billing` plan + usage meters, upgrade → Polar checkout redirect, the 402
  upgrade prompt on hitting a plan cap.
- **Teams (org)**: `<OrganizationSwitcher/>`, `/team`, create/submit an assignment, teacher
  roster (needs C1 for real names/data).
- **Telegram**: the dashboard "Connect Telegram" card → deep link → linked state (needs B1).

---

## F. Deferred / optional (record & decide, not required to launch)

- **Scanned-PDF full-page rasterization.** Scanned-PDF OCR currently covers the common case
  (each page is one **embedded image**, decoded via pypdf + Pillow). A PDF that has *neither*
  a text layer *nor* embedded page images (pure vector rendered as a page) would need
  full-page **rasterization** via a heavy binary (**poppler** or **PyMuPDF**), which was
  deliberately **not** added to keep the dependency footprint minimal. If such PDFs turn out
  to matter, add `pymupdf` (pip-only, bundles its renderer) or `pdf2image`+poppler and render
  pages in `documents/parsing._extract_page_images`. Until then such a PDF lands `ready`
  with zero chunks (no crash).
- **Clean up the old one-time Polar sandbox products** (FREE $0 / PRO $20 / Business $100,
  `recurring_interval: None`). Superseded by the recurring monthly products and wired to
  nothing (inert), but a one-time product can never drive a subscription — delete them so
  nothing points at them.
- **Final review of plan limits** (`billing/service.LIMITS`: Free 3/10/20, Pro 50/200/200,
  Business unlimited) before production launch — the sandbox products declare no caps, so
  `LIMITS` is the sole enforcer.
- **Backend org-context at runtime.** `get_org_context` reading org claims from the JWT is
  exercised by tests and (indirectly) by org-scoped endpoints; confirm once more against a
  real org-scoped request in production.
- **Phase 8 (mobile app — PWA or native)** remains deferred.

---

## Automated verification (recorded this pass — 2026-07-20)

All automated checks were run and are green; anything red was fixed before recording.

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `cd backend && pytest tests` | **536 passed, 12 deselected** |
| Backend lint | `cd backend && ruff check .` | **clean** |
| Backend format | `cd backend && ruff format --check .` | **clean (150 files)** |
| Frontend tests | `cd frontend && npm run test` | **245 passed (58 files)** |
| Frontend types | `cd frontend && npx tsc --noEmit` | **clean** |
| Frontend lint | `cd frontend && npm run lint` | **clean** |
| Migration heads | `cd backend && alembic heads` | `c1d2e3f4a5b6` |
| Migration current (Neon) | `cd backend && alembic current` | `06650625fb97` — **one behind, apply per §A** |

> The `-m live` opt-in tests (real Neon/Cohere/Anthropic) are deselected by default and are
> not part of this automated pass; run them explicitly (`pytest -m live`) if desired.
