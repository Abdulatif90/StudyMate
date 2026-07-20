# FUTURE.md — proposals & deferred work (consolidated index)

> **Status: these are FUTURE PROPOSALS, not committed work.** Phase 8 (mobile app) and
> every item below is a "nice-to-have / revisit later" — the shipped product (Phases 0–7)
> is feature-complete for the portfolio goal. Nothing here blocks launch. The user's
> standing stance (see `MEMORY`): *keep it simple — prefer the simple best-practice option,
> defer complex integrations and record them here for a post-project review.*

This file is the single **consolidated index** of every not-yet-built idea scattered across
`docs/PROGRESS.md` and `docs/WORKLOG.md` (markers: `TODO`, `deferred`, `not started`,
`future`, `follow-up`, `deliberately NOT`, `out of scope`, `kept simple`). It does **not**
replace those docs — `PROGRESS.md` stays the historical record with full inline context;
this is just the grouped, de-duplicated to-do map.

**Not here on purpose:** live/key/webhook/browser steps needed to *launch what already
exists* live in [`docs/RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) (apply the pending Neon
migration, register the Telegram/Polar webhooks, add `CLERK_SECRET_KEY`, one browser
click-through, etc.). FUTURE.md is for *new capabilities not yet built*; the release
checklist is for *shipping the built ones*. A few items overlap (plan-limit review, old
Polar product cleanup) and are cross-referenced rather than duplicated.

---

## 1. Product features

- **Research answer persistence.** Research mode (`app/modules/research`) answers are
  ephemeral — unlike Ask, they are not saved. Add a `ResearchSession`/answer store (like
  Ask's `Conversation`/`ConversationTurn`) plus a history UI. *Deferred:* Phase 6 shipped
  as a focused web-only first increment. *Effort:* medium — new model + migration + list/get
  endpoints + a frontend history surface.
- **Combine web research with the user's own RAG documents.** Research is web-only today;
  a "research over my materials + the web" mode would blend Tavily results with retrieval
  over the user's chunks. *Deferred:* out of scope for the first Research increment.
  *Effort:* medium — retrieval + prompt fusion, no new storage.
- **Telegram answering over org-shared subjects (not just the user's own).** The Telegram
  bot's Ask path is deliberately scoped to the linked user's **own private** subjects (an
  empty `OrgContext`, since a Telegram chat carries no Clerk org session) so it can never
  reach another user's or an org's content. Letting a linked teacher/student answer over
  their **org-shared** subjects needs a way to resolve an org for a chat that has no Clerk
  session. *Deferred:* correctly fails safe today; expanding it is a design decision.
  *Effort:* medium — org resolution for Telegram + reusing the existing readable-subject
  scoping.
- **Telegram "Connect" card live status (no manual refresh).** After linking in Telegram,
  the dashboard card only flips to "Connected" on a manual page refresh (no push/poll this
  increment). *Deferred:* kept simple. *Effort:* small — a poll or a webhook-driven signal.

## 2. B2B / Teams

- **Per-student assignment targeting.** Assignments broadcast to the **whole active org**
  only; there is no way to target specific members. *Deferred:* the org-broadcast model was
  the simple first cut. *Effort:* medium — a targeting model (assignment↔member rows or a
  target set) + create-form UI + read-scoping changes.
- **Team plan seat-count enforcement.** An active Team subscription lifts **every** member
  of the org to Team (unlimited) entitlements **regardless of how many seats were
  purchased** — seat count vs member count is not enforced (a deliberate simplification,
  noted in `billing/service` and `config.py`). *Deferred:* kept simple for the portfolio.
  *Effort:* medium — read Polar's purchased-seat count and compare against Clerk membership
  count, then gate/over-quota; touches the webhook + entitlement resolution.

## 3. Billing

- **Final review of plan limits before production** (`billing/service.LIMITS`: Free
  3/10/20, Pro 50/200/200, Business unlimited). The sandbox Polar products declare no caps,
  so `LIMITS` is the sole enforcer. *Cross-ref:* `RELEASE_CHECKLIST.md` §F — a launch-gate
  review, not a feature.
- **Clean up the old one-time Polar sandbox products** (FREE $0 / PRO $20 / Business $100,
  `recurring_interval: None`), superseded by the recurring monthly products and wired to
  nothing. *Cross-ref:* `RELEASE_CHECKLIST.md` §F — an ops cleanup.

## 4. i18n

- **Native review of `uz` / `ko` / `ru` catalogs.** The drafts are machine/LLM-generated
  starting points, not production-quality (especially Russian plural forms). Highest-priority
  i18n item before any non-English locale is user-facing "for real". *Effort:* small
  (review) — needs a human native speaker, not code.
- **Typed next-intl messages** (augment next-intl's `Messages` type from `en.json` so keys
  are type-checked). *Deferred:* needs a broader refactor first — ~13 call sites use dynamic
  template-literal keys (`` t(`...`) ``) that the `Messages` augmentation can't typecheck
  cleanly. *Effort:* medium — refactor the dynamic-key call sites, then enable the
  augmentation. Not started.
- **Clerk Uzbek UI localization.** `@clerk/localizations` ships `enUS`/`koKR`/`ruRU` but
  **no Uzbek** resource, so `uz` falls back to English inside Clerk's sign-in/sign-up widget
  (the rest of the app renders in Uzbek). *Deferred:* blocked upstream — revisit if/when
  Clerk adds an Uzbek resource. *Effort:* trivial once upstream exists.

## 5. Infra / OCR

- **OCR full-page rasterization of vector, text-less PDFs.** Scanned-PDF OCR currently
  covers the common case (each page is one **embedded image**, decoded via pypdf + Pillow
  and run through Claude vision). A PDF with *neither* a text layer *nor* embedded page
  images (pure vector rendered as a page) would need full-page **rasterization** via a heavy
  binary — **poppler** (`pdf2image`) or **PyMuPDF** (`pymupdf`, pip-only, bundles its own
  renderer). *Deferred:* deliberately **not** added to keep the dependency footprint minimal
  and avoid a system binary; such a PDF lands `ready` with zero chunks (no crash) today.
  *Effort:* small once a dependency is chosen — render pages in
  `documents/parsing._extract_page_images` and reuse the existing Claude-vision OCR path.
  *Cross-ref:* `RELEASE_CHECKLIST.md` §F.

## 6. Mobile — Phase 8 (deferred)

- **Mobile app (PWA or native).** Roadmap Phase 8, explicitly deferred throughout the build
  — revisit after the web app is launched and validated. *Effort:* large (a PWA pass is the
  simpler option: manifest + service worker + install prompt over the existing responsive
  Next.js app; a native app is a separate project). No work started.

---

*When an item here gets built, move its full write-up into `PROGRESS.md`/`WORKLOG.md` as
usual and strike it from this index.*
