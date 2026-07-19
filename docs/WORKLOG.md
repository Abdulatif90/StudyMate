# Worklog

Log of completed work (newest first). Each entry: what was done, tests, commit.

## 2026-07-20 — Teams: Team Plan upgrade UI for org admins (Phase 5)
Frontend-only close-out of the seats feature: `/billing` gained a "Team Plan" upgrade
card, gated to org admins, so an admin can actually subscribe their org from the app
instead of only via a raw API call.
Commit: `feat(teams): Team Plan upgrade UI for org admins (Phase 5)`.

- **Step 0.** Regenerated `frontend/src/lib/api/schema.d.ts` from the live `:8000`
  `openapi.json` (`npm run generate-api-types`) — confirmed `POST /billing/team-checkout`
  takes `TeamCheckoutCreateRequest` (`success_url?: string`) and returns the SAME
  `CheckoutCreateResponse` (`{ checkout_url: string }`) shape as the individual checkout.
  Read the existing `/billing` page's `checkout` mutation to mirror it exactly: `POST
  /billing/checkout` → `onSuccess` fires `captureEvent` then `window.location.href =
  data.checkout_url`; errors render as an inline `text-sm text-destructive` paragraph
  (there's no toast call anywhere in this app despite a `components/ui/toast.tsx`
  existing, so inline error text — not a toast — is the actual established pattern, and
  that's what got mirrored). Confirmed the org-admin gate pattern from
  `assignments/page.tsx`: `useOrganization()` → `orgCapability(membership?.role)`.
- **New `lib/teamUpgrade.ts`** — pure `canShowTeamUpgrade(hasActiveOrg: boolean, role:
  string | null | undefined): boolean`, `hasActiveOrg && isTeacherRole(role)`. UX-only
  mirror of the backend's real `require_teacher` guard on `POST /billing/team-checkout`;
  a plain member or a signed-in user with no active org never sees the card. New
  `lib/teamUpgrade.test.ts` (4 cases: admin+org, member+org, admin+no-org, unknown role).
- **`/billing/page.tsx`**: added a `teamCheckout` mutation (`POST
  /billing/team-checkout`, `success_url` = `/billing?upgraded=1`, same redirect-on-success
  as the individual `checkout` mutation) and a gated `Card` — "Team Plan" title,
  "$10/seat/month" price, one-line benefit, "Upgrade to Team" button (disabled + shows
  "Redirecting…" while pending, reusing the existing `Billing.redirecting` key), inline
  destructive-text error on failure. Individual plan/checkout UI, usage meters, and the
  referral card are untouched.
- **Fallout from regenerating the client**: the backend's `Plan` enum already included
  `"team"` (shipped in the prior backend-only increment below), which the OLD hand-typed
  client didn't reflect. Regenerating surfaced 4 `tsc` errors — three `Record<Plan, …>`
  maps (`PLAN_LABELS` in `lib/planLimits.ts`; `PLAN_PRICE`/`PLAN_FEATURES_KEY`/
  `CHECKOUT_TARGETS` in `billing/page.tsx`) stopped being exhaustive. Fixed with `team`
  entries: `PLAN_LABELS.team = "Team"` is load-bearing (an org member's `GET
  /billing/plan` can now read back `"team"` as their effective individual plan value, and
  that label feeds the existing "Current plan" badge unchanged). The other three are
  unreachable stubs — the individual compare-grid's `PLAN_ORDER` constant still lists
  only `free/pro/business`, so this does NOT change the individual-checkout UI's actual
  rendered behavior, just satisfies TS.
- **i18n**: new `Billing.teamPlan.{title,price,benefit,cta}` keys, added to `en.json` and
  mirrored via targeted anchored edits (not a full JSON round-trip) into `uz.json`
  (`Jamoa tarifi` / `$10 / o'rin / oyiga` / ...), `ko.json` (`팀 요금제` / `좌석당 $10 / 월` /
  ...), `ru.json` (`Командный тариф` / `$10 / место / в месяц` / ...).
- **Checks**: `npm run test` — **237 passed** across 56 files (was 233/55 — +1 new test
  file, +4 tests), including the new `teamUpgrade.test.ts` and the existing
  `messages.test.ts` key-parity check across all 4 locales. `npx tsc --noEmit` clean.
  `npm run lint` clean. No `next build` run (dev server owns `:3000`).
- **Not yet browser-verified** (standing no-browser gap, batched to the user's
  project-end pass per `blockers_deferred_to_end.md`): the actual click → Polar-hosted
  checkout → redirect-back round trip for the Team Plan card.
- **With this, Phase 5 (Business/Teams B2B) is fully complete** — org
  foundation, org-scoped subject sharing, flashcard/quiz org read-through, shared-subject
  delete cascade, assignments (create/submit/roster, org-broadcast only), graded quiz
  attempts, and now Team Plan billing seats end-to-end (backend + this UI). The only
  remaining project-wide item is the batched real-browser click-through pass noted
  throughout this log.

## 2026-07-20 — Teams: org/team billing seats — Team Plan subscription + org-aware entitlements (Phase 5)
An org admin can now subscribe the whole organization to the Polar **Team Plan**, lifting
every member to Team (unlimited) entitlements. Backend only; the team-upgrade UI is a
separate follow-up.
Commit: `feat(teams): org/team billing seats — Team Plan subscription + org-aware entitlements (Phase 5)`.

- **Step 0 verified against the REAL Polar API before writing code.** Re-introspected the
  Team product's price via `products.get(POLAR_PRODUCT_ID_TEAM)`: `name="Team Plan"`,
  `is_recurring=True`, `recurring_interval=MONTH`, not archived — a genuine recurring
  monthly SUBSCRIPTION (so the existing `subscription.active/.updated` grant +
  `subscription.revoked` revoke model applies unchanged, NOT a one-time `order.paid`
  product). Its single price is `ProductPriceSeatBased`: `seat_tiers` = one volume tier
  `{min_seats:1, price_per_seat:1000, max_seats:null}`, `minimum_seats:1`, currency `usd`
  — i.e. **$10.00/seat/month, per-seat, no cap.** Per the task this does NOT change the
  design (an active team subscription grants ALL members Team tier regardless of seat
  count); recorded as a deliberate simplification + TODO (we do not enforce seat count vs
  member count this increment).
- **Model + migration.** New `OrgPlan(org_id PK, plan, updated_at)` — the org analogue of
  `UserPlan`, absence-of-row = Free, additive (never lowers a `UserPlan`). Added
  `Plan.TEAM = "team"` and a `Plan.TEAM` LIMITS entry mirroring Business (unlimited on
  every dimension). Registered `OrgPlan` in `alembic/env.py`. Migration `6c9f0c767feb`
  (down_revision = prior head `b2c3d4e5f6a7`): the tricky part is the shared Postgres
  `plan` enum already existed (from `user_plans`) without `team`, so autogenerate's
  implicit `CREATE TYPE` fails — hand-adjusted to `ALTER TYPE plan ADD VALUE IF NOT EXISTS
  'team'` first, then `create_table('org_plans')` referencing the existing type via
  `postgresql.ENUM(name='plan', create_type=False)` (the generic `sa.Enum(create_type=
  False)` was tried first and ignored the flag inside `create_table`, re-emitting the
  failing CREATE TYPE — switched to the dialect ENUM). **APPLIED to Neon and verified**:
  `alembic current` == `6c9f0c767feb`, `org_plans` regclass present with columns
  `org_id/plan/updated_at`, and the `plan` enum now lists `free,pro,business,team`.
- **Org-vs-user routing by a NAMESPACED external_id (the security-relevant bit).**
  `create_team_checkout(org_id)` plants `external_customer_id = "org:<org_id>"` (Clerk
  user/org ids use `_` and never a literal `:`, so no collision). The webhook's
  `resolve_subscription_event` now returns a `ResolvedSubscriptionEvent(is_org, subject_id,
  plan, event_at)` — it routes by whether the verified `external_id` starts with `"org:"`:
  org → `apply_org_subscription_event` (upserts `OrgPlan`), else the existing
  `apply_subscription_event` (`UserPlan`). The two paths can NEVER touch each other's table.
  `plan_for_product_id` also maps `POLAR_PRODUCT_ID_TEAM → Plan.TEAM`. Same grant/revoke
  event sets, entitled-status check, and `event_at` idempotency/stale-ordering guard as the
  user path; org revoke → `Plan.FREE` (members fall back to their individual plans), row
  kept (not deleted) for the same ordering-guard reason. Existing webhook signature
  verification untouched.
- **Org-aware entitlement resolution (the wide change).** New `effective_plan(session,
  owner_id, org_ctx)` = the HIGHER-ranked of the caller's own `UserPlan` and their active
  org's `OrgPlan` (`_PLAN_RANK`: Free<Pro<Business<Team). `get_limits`,
  `ensure_can_create_subject`, `ensure_can_upload_document`, `ensure_can_generate`, and
  `effective_generations_per_day` now all resolve from `effective_plan` and take an optional
  `org_ctx` (defaulting to None → exactly the legacy individual behavior). The referral
  bonus still stacks on top of the effective cap where it's finite, and stays `None`
  (unlimited) under Team. **Call sites threaded** (all already carried an `OrgContext`):
  `subjects.service.create_subject`, `documents.service.create_document`,
  `quiz.service.generate_quiz`, `flashcards.service.generate_flashcards`. Limit errors now
  name the EFFECTIVE plan. `GET /billing/plan` deliberately still reports the individual
  plan (adding org context there is a frontend-increment concern; leaving it avoids
  changing the existing plan-endpoint tests / needing an org dependency they don't override).
- **Checkout + router.** `Settings.polar_product_id_team` (documented in `.env.example`).
  `POST /billing/team-checkout` (`require_teacher`; plain member / no active org → 403),
  thin, `PolarConfigError`→500 / `PolarCheckoutError`→502 like the individual checkout, org
  id taken from the caller's verified token (never client-supplied).
- **Tests (offline, Polar client mocked, real HMAC signatures).** `test_polar.py` +12:
  team checkout plants `org:<id>`/forwards success_url/config-error when product unset/wraps
  failure; endpoint requires teacher (member→403, no-org→403); a team-product `active` with
  `external_id="org:X"` upserts `OrgPlan(X)=Team` and NO `UserPlan`; org revoke→Free; per-org
  idempotency + stale-ordering guard; org-scoped (one org can't touch another); a user event
  still writes `UserPlan` and never an `OrgPlan`. `test_billing.py` +7: `effective_plan`
  no-org = individual; org Team lifts a Free member; max-of-both both directions; Team gives
  a Free member unlimited subject + generation limits; org plan scoped to its own org;
  referral bonus still applies under a finite org tier; over-cap error names the effective
  plan. Suite **460 passed / 11 deselected** (was 441), `ruff check .` + `ruff format
  --check .` clean.

## 2026-07-20 — Teams: assignment roster UI — who has/hasn't submitted (Phase 5)
Frontend follow-up to the roster-diff backend increment above: surfaces
`GET /assignments/{id}/roster` in the teacher's existing `/assignments` submissions view.
Commit: `feat(teams): assignment roster UI — who has/hasn't submitted (Phase 5)`.

- **Step 0 verified before writing UI code.** Regenerated the typed client against the
  live backend (`npm run generate-api-types`, backend already running on :8000) — confirmed
  the real shape in `schema.d.ts`: `AssignmentRoster = { assignment_id, total_members,
  submitted_count, not_submitted_count, submitted: RosterMember[], not_submitted:
  RosterMember[] }`, `RosterMember = { user_id, submitted, score?, completed_at? }`. The
  precomputed counts meant no client-side "N of M" derivation was needed at all.
- **Name resolution — no new backend call.** The roster returns opaque Clerk `user_id`s;
  confirmed `useOrganization({ memberships: { pageSize: 100 } })` (Clerk SDK,
  `@clerk/shared`'s `OrganizationMembershipResource`) already exposes `publicUserData.{
  userId, identifier, firstName, lastName}` for every org member, so no extra roundtrip was
  needed. `src/lib/rosterMemberName.ts` (`resolveMemberName`) is a pure helper — matches a
  `user_id` against the loaded membership list and prefers full name → identifier → a
  shortened id (`user_2c9…`) — kept structurally typed (`RosterMembershipLike`, not a direct
  Clerk SDK import) to stay dependency-free, matching this codebase's existing
  `assignmentQuizStatus.ts`/`MinimalSubmission` pattern. `pageSize: 100` is a known,
  accepted simplification (no infinite pagination) — fine for a portfolio project's org
  sizes; falls back to the shortened id if a member isn't in the loaded page.
- **`src/app/(app)/assignments/page.tsx`.** Added a `rosterQuery` (`useQuery`, `enabled:
  isTeacher && !!expandedId`, `retry: false` — a 503/502 won't resolve by retrying) fetched
  alongside the existing `submissionsQuery` when a teacher expands an assignment. Render:
  a second bordered section (same visual weight as the existing submissions box) showing
  "{submitted} of {total} submitted", then two stacked-on-mobile/side-by-side-on-`sm`+
  groups — **Not submitted** (names only) and **Submitted** (name + score when present).
  Existing submissions list, student view, create form, delete, and the graded-quiz flow
  are all untouched.
- **Graceful states, not a toast.** `RosterFetchError` (a small `Error` subclass carrying
  the real HTTP status) is thrown from the query so the render layer can distinguish
  outcomes without losing the status code openapi-fetch's parsed `error` body doesn't
  carry. `src/lib/rosterStatus.ts` (`classifyRosterError`) is the pure classifier: 503 →
  "Roster unavailable" (Clerk not configured — a standing capability gap), 502 or anything
  else → "Couldn't load roster" — both a quiet inline note per FRONTEND.md's toast-vs-inline
  rule (§3.2), never an error toast, never blocking the submissions list above it from
  rendering.
- **i18n.** 7 new keys (`Assignments.rosterLabel`, `rosterSummary`, `rosterUnavailable`,
  `rosterLoadError`, `notSubmittedLabel`, `submittedLabel`, `rosterAllSubmitted`) added to
  `messages/en.json` and mirrored into `uz`/`ko`/`ru` via targeted anchored edits (not a
  full JSON round-trip); reused `Assignments.scoreLabel`/`noSubmissionsYet` and
  `Common.loading` where existing copy already fit exactly. `messages.test.ts` parity green.
- **Tests.** Two new pure-helper suites: `rosterMemberName.test.ts` (6: full name, first-name-
  only, identifier fallback, shortened-id fallback for an unmatched/null/undefined
  membership list, missing `publicUserData`) and `rosterStatus.test.ts` (4: 503, 502, other
  statuses, undefined). The page itself follows this codebase's established
  page-untested/helpers-tested convention (tsc/eslint, no browser here).
- **Verified:** `npm run test` → **233 passed** (55 files, +2 new suites, +10 tests over the
  prior 223/53). `npx tsc --noEmit` → clean. `npx eslint .` → clean (no output). `next build`
  intentionally NOT run per this session's instructions (dev server was live on :3000).
- **Deviation from the task's literal ask, flagged:** the task said "Show submitted members
  with their score" as part of the SAME compact roster summary as "Not submitted" — rather
  than folding this into the pre-existing raw submissions list (which shows unresolved
  `owner_id`s), a distinct second bordered section was added below it, so the existing,
  already-tested submissions block stays completely untouched. Net effect: the teacher now
  sees submissions twice in different forms (raw list, then the resolved-name roster) when
  expanded — accepted as the simpler, lower-risk option; a follow-up could fold the raw
  list into the roster's own "Submitted" group if the duplication proves undesirable.
- **Still owed:** no browser available in this environment — batched into the standing
  no-browser gap (`docs/PROGRESS.md`, `blockers_deferred_to_end.md`). Also inherits the
  backend's own blocker: a real `CLERK_SECRET_KEY` is needed in `backend/.env` before the
  roster returns real data instead of a 503, in whichever environment goes live.

## 2026-07-20 — Teams: assignment submission roster via Clerk org members (Phase 5)
The teacher's submissions view could only list submissions that EXIST — it couldn't show
WHO HASN'T submitted, because our DB doesn't store org membership (Clerk owns it, ADR #9).
This increment adds the roster diff: enumerate an org's members via Clerk, diff against
existing submissions. Backend only — frontend is a separate later increment. Commit:
`feat(teams): assignment submission roster via Clerk org members (Phase 5)`.

- **Architectural expansion — call it out.** Until now the backend NEVER called Clerk's
  API: `app/core/auth.py` only *verifies* the session JWT against Clerk's JWKS, and
  `app/core/org.py` only reads claims out of an already-verified token (ADR #9 — "we only
  read JWT claims"). A roster requires *enumerating* members, which only Clerk can answer.
  This is a deliberate, flagged widening of that boundary, kept isolated behind ONE client
  module (`app/core/clerk_api.py`) and env-gated so the rest of the app is unaffected —
  and, when the key is unconfigured, unbroken.
- **Verified the external contract BEFORE coding (Step 0, no guessing).** Confirmed against
  Clerk's official Backend API OpenAPI spec (`bapi/2024-10-01.yml`, source:
  `raw.githubusercontent.com/clerk/openapi-specs/main/bapi/2024-10-01.yml`, operationId
  `ListOrganizationMemberships`): endpoint `GET https://api.clerk.com/v1/organizations/
  {organization_id}/memberships`; auth `Authorization: Bearer <secret key>` (bearerAuth,
  `sk_<env>_<value>`); pagination `limit` (1–500, default 10) + `offset` (default 0);
  response `OrganizationMemberships` = `{ data: OrganizationMembership[], total_count: int }`
  (both required); each `OrganizationMembership.public_user_data.user_id` (string, required)
  is the member's Clerk user id. All five facts read directly from the spec's schema
  definitions (not the SDK-doc paraphrase, which uses camelCase), so the REST field names
  the client uses (`data`, `total_count`, `public_user_data.user_id`) are exact.
- **`app/core/clerk_api.py` (new).** `list_organization_member_ids(org_id) -> list[str]`
  walks `offset` in pages of 100 until `total_count` is read, extracting
  `public_user_data.user_id`. Missing `CLERK_SECRET_KEY` → `ClerkConfigError` at point of
  use (same loud-failure pattern as `embedding.py`/`llm.py`/`r2_client.py`/
  `inngest_client.py`); a non-2xx from Clerk → `ClerkAPIError`. ALL Clerk-REST specifics
  (base URL, bearer header, paging, JSON shape) live here and nowhere else.
- **`assignments/service.py`.** `build_roster_diff(member_ids, submissions)` is the PURE,
  I/O-free diff (members − submitters) → `(submitted, not_submitted)` lists of `RosterMember`;
  it also surfaces an ex-member submitter (submitted then left the org — an `owner_id` not
  in the member list) rather than dropping their result. `get_submission_roster(...)` runs
  the SAME teacher-gate as `list_submissions` (assignment in caller's active org via
  `get_assignment` → else 404; caller must be teacher/admin → else 403) BEFORE any Clerk
  call, then fetches members (Clerk) + submissions (DB) and assembles `AssignmentRoster`.
- **`assignments/router.py`.** `GET /assignments/{id}/roster` (thin, error-translating):
  404 cross-org, 403 plain member, **503** when `CLERK_SECRET_KEY` is unset ("roster
  unavailable — Clerk not configured" — chosen over a 500 leak, since a missing key is a
  config gap not a fault), 502 on an upstream Clerk failure.
- **Config + env.** Added optional `clerk_secret_key: str | None = None` to `Settings` and
  documented `CLERK_SECRET_KEY` in `backend/.env.example` (Phase 5 section). Distinct from
  the existing `clerk_jwks_url`/`clerk_issuer`: those verify JWTs, this calls the API.
- **No schema change → no migration.** Confirmed: the roster is COMPUTED at request time
  (Clerk members diffed against existing `AssignmentSubmission` rows), never stored.
- **Tests (offline, network-free — Clerk MOCKED, never called for real).** `test_roster_diff.py`
  (8 pure-diff cases: {A,B,C}∩{A}, empty members, all/none submitted, ex-member submitter,
  dedupe, order). `test_clerk_api.py` (5: missing-key raises BEFORE any network via a
  transport that would assert on a real call; single-page extraction; pagination across two
  pages; non-200 → `ClerkAPIError`; asserts the on-the-wire path + bearer header match the
  verified contract, using `httpx.MockTransport`). `test_assignment_roster.py` (7 endpoint:
  teacher gets the diff, none-submitted, 403 plain member + 404 cross-org BOTH proven to run
  before any Clerk call, missing-key→503, upstream→502, ex-member surfaced).
- **DEVIATION — flag for review.** The task premise said "no Clerk secret key is set here";
  in fact `backend/.env` DOES contain a live `CLERK_SECRET_KEY=sk_test_...`. I did NOT touch
  `.env` and do not reproduce the value. Consequence: the missing-key path can't be proven
  by simply having no key in this env, so it's proven deterministically instead — the client
  unit test overrides settings to `None` (real `ClerkConfigError`, no network), and the
  endpoint test mocks the client to raise `ClerkConfigError` (real 503 translation). No test
  ever hits real Clerk. The app + full suite still boot/pass exactly as required — verified.
- **Tests: backend 441 passed, 11 deselected (live), 0 failed** (`pytest tests`); `ruff
  check .` clean; `ruff format --check .` clean (128 files). No frontend touched.

## 2026-07-20 — Teams: graded quiz flow UI (Phase 5 increment 4b)
Frontend half of 4a — wires the quiz-taking page and the assignments student view to the
new server-graded attempt endpoint, replacing the manual self-reported score/note. Commit:
`feat(assignments): graded quiz flow UI — take quiz, auto-score, auto-complete (Phase 5
increment 4b)`.

- **Quiz page persists the attempt.** `subjects/[subjectId]/quizzes/[quizId]/page.tsx`'s
  "Check answers" button now, alongside the existing instant client-side reveal, fires a
  mutation that POSTs `{ answers }` to `.../quizzes/{quizId}/attempts` (body built by a new
  pure helper `toAttemptRequestBody` in `lib/quizScore.ts`, unit-tested). The visible score
  stays client-computed — the server grades identically off `correct_index`, so nothing
  about the reveal UX or per-question styling changed. A failed save doesn't block the
  reveal, it toasts `QuizDetail.attemptSaveErrorTitle`. On success it invalidates the
  `["assignments"]` query-key prefix, which covers both the assignments list and every
  per-assignment `["assignments", id, "my-submission"]` query, so a linked assignment shows
  the new score on return without a manual refresh.
- **Assignments student view drops the manual score/note form.** New pure helper
  `lib/assignmentQuizStatus.ts` (unit-tested, 4 branches) classifies each card:
  `quiz-not-started` / `quiz-completed` (carries the real graded score) for a quiz-linked
  assignment (`quiz_id != null`), or `manual-not-done` / `manual-done` for a plain one. A
  quiz-linked assignment now shows "Not started" + a "Take quiz →" link into the existing
  quiz page, or "Completed · score N" once the auto-completed submission exists — the score
  is never self-reported. A non-quiz assignment keeps a simple "Mark as done" button
  (`POST /assignments/{id}/submit` with `score`/`note` both null) instead of the old numeric
  input. Teacher view (create/list/submissions/delete) and the quiz page's per-question
  reveal styling are both untouched, as scoped.
- **Typed client regenerated** against the live backend (`npm run generate-api-types` →
  `openapi-typescript` against `:8000/openapi.json`) to pick up `QuizAttemptRequest`,
  `QuizAttemptResult`, and the new `/subjects/{subject_id}/quizzes/{quiz_id}/attempts` POST
  path shipped in 4a — confirmed `answers` is `{[key: string]: number}`, matching the quiz
  page's existing `QuizAnswers` state shape exactly (no transform needed beyond the wrapper).
- **i18n**: added `QuizDetail.attemptSaveErrorTitle` and
  `Assignments.{takeQuiz,notStarted,completedLabel,markAsDone}`; removed the now-dead
  `Assignments.{scoreOptionalLabel,noteOptionalLabel,markComplete}`. All four locales
  (en/uz/ko/ru) kept in parity via targeted anchored edits (no full-file JSON round-trip,
  per the prior reflow-bug lesson).
- **Tests**: frontend 223/223 passing (53 files — 2 new: `assignmentQuizStatus.test.ts`, plus
  new cases in `quizScore.test.ts`), `tsc --noEmit` clean, `eslint` clean. No `next build`
  run (dev server owns :3000). Not yet browser-verified — batched into the user's
  project-end no-browser blocker pass (`blockers_deferred_to_end.md`), consistent with every
  other frontend-only increment so far.

## 2026-07-20 — Teams: server-graded quiz attempts + auto-complete linked assignments (Phase 5 increment 4a)
Backend half of the "auto-grading / quiz-attempt linkage" that 3b left as a TODO. Commit:
`feat(quiz): server-graded quiz attempts + auto-complete linked assignments (Phase 5 increment 4a)`.

- **Server-authoritative grading — no trusted client score.** New endpoint
  `POST /subjects/{subject_id}/quizzes/{quiz_id}/attempts` takes only `answers` (question id
  → chosen option index); there is deliberately NO score field in `QuizAttemptRequest`. The
  score is computed in `quiz.service.grade_and_record_attempt` against each
  `QuizQuestion.correct_index` — a question is correct only when the submitted index equals
  `correct_index`. Defensive by design: unknown question ids in `answers` are ignored, and a
  missing or out-of-range index counts as wrong, never a 500. `total` is the number of
  questions. A test posts bogus `correct`/`score`/`total` alongside wrong answers and proves
  the server ignores them and grades 0/2.
- **Access reuses the quiz reader path.** Authorization goes through the exact same
  `get_quiz_for_reader` used to read a quiz: a student may attempt a teacher's SHARED
  org-subject quiz (graded against the quiz OWNER's questions, like
  `list_questions_for_reader`), but a non-readable quiz — cross-org, or another student's
  private quiz on the same shared subject — raises `QuizNotFoundError` → 404, so a caller
  can't even probe for it.
- **One attempt row per (quiz, student), UPSERTED.** New `QuizAttempt` model (owner = the
  student; `subject_id` denormalized from the quiz for tenant-scoping without a join), unique
  on `(quiz_id, owner_id)` (`uq_quiz_attempt_quiz_owner`). A re-attempt overwrites the same
  row (latest wins, `submitted_at` advanced) — no duplicate, no full history this increment.
- **Quiz → assignment auto-completion, wired at the ROUTER (not service→service).** After
  grading, the quiz router calls `assignments.service.record_quiz_completion(session,
  owner_id, org_ctx, quiz_id, result.correct, result.total)`. This router-level
  orchestration is the deliberate wiring choice: quiz.service does NOT import
  assignments.service and vice-versa, so there is no module cycle — the router owns the
  two-step flow (grade + store attempt, then sync submissions). `record_quiz_completion`
  UPSERTS the student's `AssignmentSubmission` (via the shared `_upsert_submission` helper,
  `score = correct count`, `note = None`, marked complete) for EVERY assignment where
  `quiz_id` matches AND `org_id == caller's active org`. No linked assignment (or no active
  org) → a no-op returning `[]`: the attempt is still recorded, it just completes nothing.
  Fails closed on no active org (an assignment's `org_id` is never NULL, so a `None` active
  org can't match).
- **Manual submit untouched.** `POST /assignments/{id}/submit` (3b) still works for non-quiz
  assignments — a test seeds a quiz-less assignment and marks it complete with a self-reported
  score/note through the manual path, unchanged.
- **Migration APPLIED to Neon.** New table `quiz_attempts` (hand-written migration
  `b2c3d4e5f6a7`, `Revises: a1b2c3d4e5f6`). Single head; Neon was at `a1b2c3d4e5f6` and
  brought to head — `alembic current` == `b2c3d4e5f6a7`. Verified via SQLAlchemy inspector
  that `quiz_attempts` exists on Neon with its 7 columns, the `uq_quiz_attempt_quiz_owner`
  unique constraint, and the quiz_id/subject_id/owner_id indexes. The live app needs the
  table immediately (a missing table would be a live 500 on the first attempt).
- **Tests (offline, isolated SQLite + dependency-overrides).** 13 new tests in
  `test_quiz_attempts.py`: grading correctness (full/partial/unanswered/out-of-range),
  client-can't-inflate, attempt upsert (single row, latest wins), access (student attempts
  shared teacher quiz, nonexistent→404, cross-org→404, other student's private quiz→404), and
  auto-completion (linked quiz completes with the graded score, unlinked records attempt but
  no submission, manual submit still works, no cross-org completion leak). Backend **422
  passed / 11 deselected**, `ruff check` + `ruff format --check` clean. (Fixed only the prior
  builder's un-run `ruff format` on the 4 touched files — pure line-reflow, no logic change.)

## 2026-07-20 — Referral reward grant — bonus daily generations (Phase 4 completion)
Closes the last open Phase 4 item (attribution existed since the referral increment; this
adds the actual reward). Commit:
`feat(referral): bonus daily generations reward (Phase 4 completion)`.

- **Reward model chosen: DERIVED bonus, no new table, no Polar.** Every genuine referral
  grants the referrer `BONUS_PER_REFERRAL = 5` bonus daily generations. The bonus is a pure
  function of the existing `ReferralAttribution` rows — `bonus = count_referrals * 5` — so
  there is **no stored reward state** to keep consistent and **nothing touches Polar**. Of
  the three options previously listed (bonus generations / plan credit / Polar discount) this
  is the KISS portfolio choice: an internal entitlement tweak that reuses everything already
  built.
- **Why it's abuse-safe with NO new guard.** Because the reward derives entirely from
  attribution rows, it inherits that layer's existing guards automatically: self-referral is
  blocked (400), a referee can be attributed at most once (DB unique on `referred_owner_id`),
  and a referee can't switch referrers. There is no new surface to abuse — you can only raise
  your cap by genuinely referring distinct new accounts. This reasoning is documented in
  comments in both `billing.service` and `referral.service` so the reviewer sees it's
  deliberate, not an oversight.
- **Single source of truth for the effective cap.** New
  `billing.service.effective_generations_per_day(session, owner_id) -> int | None`: returns
  `None` for Business (unlimited stays unlimited — a bonus on `None` is meaningless), else
  `plan_cap + count_referrals * BONUS_PER_REFERRAL`. `ensure_can_generate` now enforces this
  effective cap, and `GET /billing/plan` surfaces it in `limits.max_generations_per_day`, so
  the enforced cap and the displayed usage-meter cap can never disagree. `record_generation`
  / counting are unchanged.
- **Module wiring / import direction.** `billing.service` imports `count_referrals` from
  `referral.service` at module level (billing depends on the referral count — the natural
  direction). `referral.service` reads `BONUS_PER_REFERRAL` back only via a **deferred**
  (function-level) import inside `get_referral_summary`, so there is no import cycle. Extracted
  `referral.service.count_referrals(session, owner_id) -> int` so the count query lives in ONE
  place (previously inline in `get_referral_summary`).
- **Surfaced reward.** `GET /referral` (`ReferralRead`) gained `bonus_generations_per_day`
  (= `count_referrals * 5`) — the bonus earned, NOT the raw effective cap (that stays in
  billing). Schema + `get_referral_summary` updated.
- **Tests (offline, isolated SQLite + dependency-overrides).**
  - `tests/test_billing.py` (+5): zero referrals → effective cap == plan cap and blocked at
    it (pins prior behavior); N attributions → effective cap == plan_cap + N*5, allowed past
    the base cap but blocked at the bonused cap (error names the raised cap); Business stays
    unlimited regardless of referrals; tenant isolation (another owner's attributions don't
    inflate mine); `GET /billing/plan` surfaces the bonused cap.
  - `tests/test_referral.py` (+2): `GET /referral` bonus is 0 with no referrals and
    `count * 5` with N (parity with the existing owner-scoped `referred_count`).
  - **Backend: 409 passed, 11 deselected.** `ruff check` + `ruff format --check` clean.
- **Frontend (one added line).** Typed client regenerated via the offline `app.openapi()`
  dump → `openapi-typescript` (schema diff purely the new `bonus_generations_per_day` field).
  `ReferralCard` on `/billing` now shows "You've earned +N generations/day" when
  `bonus_generations_per_day > 0` (new i18n key `Referral.bonusEarned`, mirrored key-for-key
  into uz/ko/ru via targeted anchored edits — no full JSON round-trip). Card left otherwise
  unchanged. **Frontend: 216 passed (52 files)**, `tsc --noEmit` + `eslint` clean.
- **No-browser gap:** the added ReferralCard line hasn't been verified in a real browser with
  Clerk auth (no browser in this environment) — it's covered by the parity test + tsc/eslint
  and the backend field is fully tested, but the rendered line itself is unverified visually.
- **No schema change / no alembic** — the reward is derived, so no new table and no migration.

## 2026-07-20 — Teams: assignment UI — teacher create + student submit (Phase 5, increment 3c)
Frontend for the assignments backend that landed in 3a+3b (commits d2af931 + cae83c9),
closing the "teacher assigns + tracks" vertical slice so it's demoable end-to-end.
**Frontend only** — no backend changes. Commit:
`feat(teams): assignment UI — teacher create + student submit (Phase 5 increment 3c)`.

- **Typed client regenerated.** The live dev backend's `/openapi.json` turned out to be
  stale (missing the assignments routes entirely — a fresh Python import of `app.main`
  had them, confirming the running `uvicorn` process just pre-dated the 3a/3b commits, not
  a code problem). Used the prompt's documented fallback instead of restarting someone
  else's dev server: dumped `app.openapi()` to a temp file and ran `openapi-typescript`
  against that. `src/lib/api/schema.d.ts` diff was purely additive (379 lines, 0 deleted) —
  confirms nothing else was dropped by using the offline snapshot.
  `AssignmentRead`/`AssignmentCreate`/`AssignmentSubmissionRead`/`AssignmentSubmissionCreate`
  and all 5 endpoints now present.
- **One role-adaptive page**, `src/app/(app)/assignments/page.tsx`, mirroring the
  `/subjects` and `/team` patterns (typed client + TanStack Query, `useConfirm` for
  delete, `toast()` for mutation errors, native `<select>` for pickers — no shadcn Select
  primitive exists in this repo, same as the language switcher).
  - **No active org**: mirrors `/team`'s empty state — an `EmptyState` with a "Go to Team"
    link, not `<CreateOrganization/>` itself (that stays Team's job).
  - **Teacher** (`orgRole` → `"teacher"`): create form (title, subject `<select>` from
    `GET /subjects`, optional description/due-date/quiz — the quiz `<select>` populates
    from `GET /subjects/{id}/quizzes` only once a subject is chosen, kept minimal per the
    task's "your call, favor simple"); the org's assignment list; per-assignment delete
    (creator-or-teacher gated) and a "View submissions" toggle that expands
    `GET /assignments/{id}/submissions` inline, explicitly labeled as "submissions
    received... not the full roster" (mirrors the backend's own documented roster
    limitation — Clerk owns membership, we can't enumerate "who hasn't submitted").
  - **Student** (plain member): the same list, each card either showing "Mark complete"
    (an inline form with optional self-reported score 0–100 + note, `POST .../submit`) or,
    once submitted, a completed badge with the date/score from `GET .../my-submission`.
    Each assignment's own-submission query treats a 404 as "not submitted" (`data: null`),
    not an error — fetched per-assignment via `useQueries`, same pattern as the Ask page's
    conversation-preview sidebar.
- **Two extracted pure helpers, unit-tested** (this codebase's page-untested/
  helpers-tested convention): `lib/assignmentPermissions.ts` (`canCreateAssignment`/
  `canDeleteAssignment`, mirroring `require_teacher` and `service.delete_assignment`'s
  creator-or-teacher gate exactly) and `lib/assignmentDueDate.ts` (`dueStatus` →
  none/upcoming/overdue, purely presentational, no backend deadline enforcement exists).
  10 new tests across the two files.
- **Nav + routing**: `lib/navItems.ts` gained an `assignments` entry (`ClipboardList`
  icon) between Team and Billing — `AppShell` already renders every `NAV_ITEMS` entry, no
  shell change needed. `middleware.ts` gained `/assignments(.*)` to the protected-route
  matcher. `navItems.test.ts` updated for the new href list.
- **i18n**: new `Assignments` namespace (40 keys) + `Nav.assignments`, mirrored into
  `uz`/`ko`/`ru` via anchored edits (not a full JSON round-trip, per the prior-increment
  formatting-reflow bug) — `messages.test.ts` catalog-parity + ICU-plural tests green.
- **Deliberately deferred** (portfolio-keep-it-simple steer, tracked in PROGRESS "Next",
  not started): admin/org billing seats (Polar per-seat) and the roster diff ("who
  HASN'T submitted" — needs a Clerk member-list API call). Neither touched.
- **No backend changes** — the API was already shipped in 3a/3b; nothing found that
  needed fixing.
- Frontend: `tsc --noEmit` clean, `eslint` clean, **216 passed** (52 files, up from 206 —
  10 new: `assignmentPermissions.test.ts` + `assignmentDueDate.test.ts`).
- **Not yet browser-verified** (no browser in this environment) — batched with every
  other frontend increment's no-browser gap; see PROGRESS "Still owed".

## 2026-07-20 — Teams: assignment completion tracking (Phase 5, increment 3b)
The "tracks" half of the roadmap's "Teacher assigns + tracks": a student marks an
assignment complete (their own per-student submission) and a teacher views the submissions
that exist for an assignment. **Backend only.** Explicitly OUT of scope (later increments,
tracked in PROGRESS): a full roster diff of "who HASN'T submitted", auto-grading / tying
completion to a real quiz attempt+score, per-student targeting, and any frontend. Commit:
`feat(teams): assignment completion tracking (Phase 5 increment 3b)`.

- **New model `AssignmentSubmission`** in the existing `assignments` module — **strictly
  owner-scoped** (CLAUDE.md rule 2), the deliberate contrast with the org-broadcast
  `Assignment`: `owner_id` is the STUDENT who acted and each student owns at most one
  submission per assignment. Presence of a row IS "completed" (no `status` column, KISS);
  `completed_at` (default now) plus optional self-reported `score`/`note`. Uniqueness on
  `(assignment_id, owner_id)` is a **real `UniqueConstraint`** (DB-enforced, not just a
  service check), so a re-submit UPSERTs the same row and a duplicate can't be written even
  under a race. Plain-FK, no ORM relationship/cascade (codebase convention).
- **Service** (all logic here, router thin): `submit_assignment` gates on the reused
  `get_assignment` (caller must READ it → in their active org, else `AssignmentNotFoundError`
  → 404) then UPSERTs the caller's row (idempotent). `list_submissions` is the TEACHER view
  — same `get_assignment` org gate PLUS `is_teacher_role` (else `SubmissionViewForbiddenError`
  → 403); returns every student's submission for the assignment. `get_my_submission` returns
  the caller's own row only (owner-scoped), org-gated first. No cross-org leak: the
  assignment is confirmed in the caller's org before any submission is read.
- **Delete cascade extended.** `delete_assignment` now deletes the assignment's
  `AssignmentSubmission` rows and flushes BEFORE deleting the parent — the same
  flush-before-parent-delete FK ordering used across this codebase (no ORM cascade to order
  it for us; deleting the assignment first would FK-violate → a loud 500). Proven by a test.
- **Roster limitation (by design, documented).** Clerk owns org membership, our DB does
  not, so the backend cannot enumerate "all students in the org" — the teacher view lists
  the submissions that EXIST (students who acted), NOT a full roster diff of who hasn't
  submitted. Same "Clerk owns membership" boundary the Assignment model already lives
  within; closing it needs a Clerk member-list call (a later increment). Recorded as a TODO.
- **Router** (thin, under the existing `/assignments` router): `POST /assignments/{id}/submit`
  (201; student marks complete; 404 if not in their org), `GET /assignments/{id}/submissions`
  (teacher view; 403 for a plain member, 404 cross-org), `GET /assignments/{id}/my-submission`
  (own row; 404 if none). Errors translated explicitly, never swallowed.
- **Migration `a1b2c3d4e5f6`** adds the `assignment_submissions` table (+ its
  UniqueConstraint and indexes on assignment_id/owner_id), `down_revision = faccee6a0508`,
  single head. **Hand-written**, not autogenerated. Model registered in `alembic/env.py`.
  **APPLIED to Neon** — verified: `alembic current` == head `a1b2c3d4e5f6`; tables
  `flashcard_review_states`, `assignments`, `assignment_submissions` exist on Neon.
- **Tests:** 16 new in `tests/test_assignments.py` (30 total in the file): student submits →
  one owned row; idempotent re-submit updates the same row (unique holds, no duplicate);
  two students each get their own row; wrong-org / no-active-org student → 404 on submit;
  out-of-range score → 422; teacher views all submissions; plain member → 403; wrong-org
  teacher → 404; `my-submission` returns own only, 404 when none / cross-org; delete cascades
  submissions (no FK violation). **Full suite: 402 passed, 11 deselected.** `ruff check` +
  `ruff format --check` clean.

## 2026-07-20 — Teams: assignment foundation — teacher assigns to org (Phase 5, increment 3a)
The "assign" half of the roadmap's "Teacher assigns + tracks". A teacher creates an
`Assignment` broadcast to their active org; every member of that org can list/read it.
**Backend only.** Explicitly OUT of scope (later increments, tracked in PROGRESS): who
*did* the assignment (completion/submission tracking), per-student targeting, and any
frontend. Commit:
`feat(teams): assignment foundation — teacher assigns to org (Phase 5 increment 3a)`.

- **New module `app/modules/assignments/`** (models + schemas + service + router, thin
  router with all logic in the service). `Assignment` carries `org_id` (creator's active
  org), `owner_id` (creating teacher), `subject_id` FK, nullable `quiz_id` FK, title,
  optional description/due_at, created_at — plain-FK columns, no ORM relationship/cascade
  (Document/Quiz convention).
- **Targeting = the whole active org.** The assignment stores `org_id` and every member
  whose ACTIVE org matches sees it — NO Clerk member-list call anywhere (Clerk owns
  membership, our DB doesn't), the same implicit-membership shape as org-owned subjects.
- **Deliberate scoping departure (documented in the service docstring):** unlike the usual
  owner-only rule (CLAUDE.md rule 2), the reads are **org-scoped** — `list_assignments` /
  `get_assignment` match `assignment.org_id == caller's active org_id`, mirroring
  `subjects.service.can_read_subject`. It fails **closed**: a caller with **no active org**
  gets an empty list / 404, and since `org_id` is NOT NULL on every row a `None == None`
  match can never leak.
- **Writes keep the strict scope.** `create_assignment` runs `require_writable_subject` on
  the target subject (so a teacher's org subject — `org_id == active org` — guarantees the
  assignment targets that org). Optional `quiz_id` is validated (`_validate_quiz_link`):
  quiz must exist, be over the SAME subject, and be **owned by the creating teacher** (per
  increment 2b a teacher's quiz over a shared subject is teacher-owned) — else
  `AssignmentQuizInvalidError` → 400, never a 500. `delete_assignment` allows the creator
  OR any teacher/admin of the assignment's org; a plain member → 403
  (`AssignmentDeleteForbiddenError`), a wrong-org/nonexistent id → 404 (existence hidden).
- **Router** wired into `app/main.py`: `POST /assignments` (`require_teacher`),
  `GET /assignments`, `GET /assignments/{id}`, `DELETE /assignments/{id}` — errors
  translated (`SubjectNotFoundError`→404, `SubjectWriteForbiddenError`→403, quiz-invalid→400).
- **Migration `faccee6a0508`** adds the `assignments` table (+ indexes on org_id/owner_id/
  subject_id/quiz_id). **Hand-written**, not autogenerated: the live Neon DB is not up to
  date (the prior `5ccf38a52dfb` flashcard-review-states revision is itself batched to the
  project-end live pass), so autogenerate refuses ("target database is not up to date").
  DDL mirrors the model and matches autogenerate's shape (cf. quizzes migration). `alembic
  heads` stays SINGLE (`faccee6a0508`). **APPLIED to Neon** (verified: `alembic current`
  == head `a1b2c3d4e5f6`; tables `flashcard_review_states`, `assignments`,
  `assignment_submissions` exist on Neon).
- **Tests** — `tests/test_assignments.py`, 17 tests, same offline isolated-SQLite +
  `dependency_overrides` + `_act_as` pattern as `test_org_quizzes.py`: teacher creates over
  an org subject; student/loner can't create (403 via `require_teacher`); private/wrong-org
  subject denied (404); quiz link happy path + rejected for other-subject / not-teacher's /
  nonexistent quiz (400); list is org-scoped (same-org member sees it, different-org member
  and no-org caller both see `[]`); `GET /{id}` 404s cross-org and for no-org; delete works
  for creator and another teacher of the org, 403 for a plain member, 404 cross-org.
- **Full suite green: 389 passed** (+11 deselected), `ruff check` clean, `ruff format
  --check` clean.

## 2026-07-19 — Teams: shared-subject delete cascade across all members (Phase 5, increment 2b — final piece)
Closes the last gap in increment 2b. Before this, `subjects.service.delete_subject`'s
cascade enumerated only the SUBJECT OWNER's children — so on a shared org subject, any
OTHER member's derived content (their own flashcards/quizzes/conversations, plus their
`FlashcardReviewState` rows over the teacher's shared cards) was left behind, and the
final `session.delete(subject)` would raise an FK violation (a loud 500), meaning a
teacher literally couldn't delete a subject other members had used. Now the cascade
cleans up EVERY member's content. **No schema change → no migration.** Commit:
`feat(teams): shared-subject delete cascade across all members (Phase 5 increment 2b)`.

- **Four cascade-only enumerators** added, one per content module — each returns ALL of a
  subject's rows regardless of owner, with NO ownership/access check, documented as
  cascade-only (same spirit as `subjects.service._get_subject_by_id`; never exposed to a
  request path): `documents.service.list_all_documents_for_subject`,
  `quiz.service.list_all_quizzes_for_subject`,
  `flashcards.service.list_all_flashcards_for_subject`,
  `ask.service.list_all_conversations_for_subject`.
- **`delete_subject` cascade rewritten** to iterate those all-owner lists and call the
  EXISTING owner-scoped `delete_*` with **each row's OWN `owner_id`** (not the subject
  owner's, not the caller's), `commit=False`. This reuses every module's child-row + R2
  cleanup unchanged: `delete_document` → chunks + R2 object; `delete_quiz` → questions;
  `delete_flashcard` → that card's `FlashcardReviewState` rows for ALL reviewers;
  `delete_conversation` → turns. Same delete ORDER (documents, quizzes, flashcards,
  conversations, then the subject) and one-transaction/`commit=False` discipline as
  before. For a private subject (owner == caller) it's identical to before — only one
  owner's content ever exists. Rewrote the docstring (the old "content OTHER members
  derived … is NOT enumerated … known limitation flagged for 2b" paragraph is now
  resolved).
- **Authorization UNCHANGED**: still `require_writable_subject` (owner, or a teacher/admin
  of the owning org); a plain member still gets `SubjectWriteForbiddenError` (→ 403); a
  non-readable subject still returns `False` (→ 404).
- **Tests** (extend `tests/test_subjects.py`): `test_delete_shared_org_subject_cascades_across_all_members`
  — teacher T owns an org subject; student member S has their own document(+chunk)/quiz(+question)/
  flashcard/conversation(+turn) on it AND a `FlashcardReviewState` over one of T's shared
  cards; T deletes → ALL rows across BOTH owners gone (incl. the review-state) and R2
  `delete_object` ran for both owners' documents. Verified this test FAILS on the old
  owner-only cascade (temporarily re-scoped the loop → the student's document survived,
  assertion caught it) and passes on the new one. Plus `test_member_cannot_delete_shared_org_subject_403`
  (member → `SubjectWriteForbiddenError`) and `test_delete_subject_not_readable_returns_false`
  (different org → `False`). The pre-existing single-owner + empty-subject cascade tests
  still pass unchanged (the enumerators filter by `subject_id`, so a *different* subject's
  other-owner content stays untouched).
  Verify: `pytest tests` → **372 passed, 11 deselected**; `ruff check .` → clean;
  `ruff format --check .` → clean.
- **Increment 2b is now COMPLETE** — flashcard read-through + quiz read-through + the
  all-members delete cascade all done. Remaining Phase 5 work is "Teacher assigns +
  tracks" and "Admin / billing seats" only.

## 2026-07-19 — Teams: quiz org read-through (Phase 5, increment 2b — quiz half)
Applies the same org-owned shared-subject read model to **quizzes** (mirrors the
flashcard half in the entry below). A member can now generate, list, and read quizzes
over a teacher's shared org subject. Quizzes have NO per-user state (no SM-2), so **no
new table and no migration** — reading returns the same content to every reader. Scope
this run = quizzes ONLY; the shared-subject DELETE cascade is now the **only** thing
left in increment 2b. Commit: `feat(teams): quiz org read-through (Phase 5 increment 2b)`.

- **Generation** (`generate_quiz`) switched from owner-only to readability-scoped and now
  takes `org_ctx`: it samples via `sample_subject_chunk_texts_for_reader` (the reader
  variant added in the flashcard half), so a student can build a quiz over a teacher's
  org subject. The `Quiz` + `QuizQuestion` rows are **owned by the caller**
  (`owner_id = caller_id`) — per-student, exactly like the flashcard side.
- **Reading** — new reader variants the router now calls, each carrying the same
  cross-student-leak guard the flashcard review fix taught: subject-readability alone is
  NOT enough — the quiz must be owned by the caller OR by the subject's owner, never
  another student's.
  - `list_quizzes_for_reader` — `require_readable_subject`, then `Quiz.owner_id in
    {caller, subject.owner}` via a `_reader_owner_filter` mirroring the flashcard one.
  - `get_quiz_for_reader` — `get_readable_subject`, fetch the quiz by id+subject_id (no
    owner filter), then reject unless `quiz.owner_id in {caller, subject.owner}` → None
    (→ 404), so a caller can't probe for another student's quiz by id.
  - `list_questions_for_reader` — resolves the quiz through `get_quiz_for_reader` FIRST,
    then lists questions filtered by the QUIZ's owner_id (the quiz owner, not the caller
    — on a shared quiz the questions belong to the subject owner, so a caller-scoped
    filter would return nothing).
  - The owner-scoped `list_quizzes` / `get_quiz` / `list_questions` are KEPT unchanged
    for `subjects.service.delete_subject`'s cascade (same discipline as the kept
    owner-scoped `list_flashcards`); that cascade needs no change.
- **Delete** (`delete_quiz`) stays OWNER-only and unchanged — a student can't delete a
  teacher's shared quiz (same 404-as-missing behavior). Router delete endpoint keeps no
  `org_ctx`.
- **Router**: read/generate endpoints (`generate_quiz`, `list_quizzes`, `get_quiz`) gain
  `org_ctx: OrgContext = Depends(get_org_context)` and call the reader variants; routers
  stay thin. Response shapes (`QuizRead` / `QuizQuestionRead` / `QuizWithQuestions`)
  are unchanged, so the frontend keeps working.
- **Tests**: new `tests/test_org_quizzes.py` (10, same isolated-SQLite +
  dependency-override + `_act_as` pattern as `test_org_flashcards.py`): member generates
  over a teacher's org subject → quiz owned by the member; loner/other-org generation
  404s; member reads the teacher's shared quiz + its (teacher-owned) questions; listing
  returns own + teacher quizzes and EXCLUDES another student's private quiz; owner sees
  only their own; **the leak-regression test** `test_member_cannot_read_another_students_private_quiz`
  (student B gets 404 on get + absence from list of student A's private quiz — verified
  it fails without the owner-set restriction); cross-org member can't list/get; delete
  owner-only. Updated the live `generate_quiz` call for the new `org_ctx` arg.
  Verify: `pytest tests` → **369 passed, 11 deselected**; `ruff check .` → clean;
  `ruff format --check .` → clean.
- **Frontend OUT OF SCOPE this run** (follow-up): `QuizRead`/`QuizWithQuestions` are
  unchanged so the existing owner UI keeps working; a student-facing "take shared quiz"
  UI is a later increment.

## 2026-07-19 — Teams: flashcard org read-through (Phase 5, increment 2b — flashcard half)
Extends the increment-2 org-read model (org-owned, read-shared subjects) from
subjects/documents/Ask to **flashcards**: a member can now generate, list, and review
flashcards over a teacher's shared org subject. Scope this run = flashcards ONLY;
**quiz org read-through and the shared-subject DELETE cascade remain out of scope**
(still owner-scoped, unchanged from PROGRESS's TODO list). Commit:
`feat(teams): flashcard org read-through (Phase 5 increment 2b)`.

- **New model wired up**: `FlashcardReviewState` (added uncommitted earlier this pass —
  a NON-owner reviewer's private SM-2 schedule; unique on `(flashcard_id, owner_id)`
  where `owner_id` is the REVIEWER). The `Flashcard` inline columns stay the OWNER's own
  schedule; a non-owner reviewer's schedule lives in a `FlashcardReviewState` row, so the
  owner and every student keep an independent schedule over the same shared card.
- **Access model = the single source of truth in `subjects.service`** (no logic
  duplicated): read/generate paths go through `require_readable_subject` (→
  `SubjectNotFoundError` → 404 when not readable); delete stays OWNER-only.
- **Generation** (`generate_flashcards`) switched from owner-only to readability-scoped
  and now takes `org_ctx`. A student generating over a teacher's org subject creates
  cards **owned by the caller** (`owner_id = caller`) — per-student ownership, exactly
  like conversations. CRITICAL companion change: added
  `documents.service.sample_subject_chunk_texts_for_reader` — verifies readability then
  samples chunk texts by `subject_id` ALONE (no `owner_id` filter), mirroring how
  increment 2 made `search_chunks` subject-scoped-with-access-check; the old owner-scoped
  `sample_subject_chunk_texts` is kept (quiz still uses it). Extracted a shared
  `_stride_sample` helper so both samplers share one down-sampling rule (DRY).
- **Listing** (`list_flashcards_for_reader` / `list_due_flashcards_for_reader`, new
  reader-scoped functions the router now calls): for caller C on subject S owned by T,
  returns C's own cards (inline schedule) plus — when C ≠ T — T's cards (schedule from
  C's `FlashcardReviewState`, or a brand-new default: due at the card's creation → due
  now, repetitions 0, default ease, when C has no state row). Another student's private
  cards are NEVER surfaced; the owner sees only their own inline-scheduled cards. `/due`
  applies the cutoff to the EFFECTIVE per-caller schedule (computed in Python because the
  effective `due_at` comes from three sources a single SQL predicate can't express; a
  `_as_naive_utc` helper reconciles naive DB datetimes with the tz-aware `now`). The
  owner-scoped `list_flashcards` is KEPT (unchanged signature) because
  `subjects.service.delete_subject`'s cascade enumerates the OWNER's cards — same pattern
  as documents' `list_documents` vs. `list_documents_for_reader`.
- **Review** (`review_flashcard`, now takes `org_ctx`, keyed by flashcard_id alone):
  fetch the card by id (no owner filter); own card → update inline columns (unchanged);
  else verify the caller can READ the card's subject (`get_readable_subject` → None → 404
  if not) then **upsert** the caller's `FlashcardReviewState` and advance THAT schedule
  via `sm2.review`, never the owner's inline columns. The unique constraint guarantees
  one row per (card, reviewer), so two students stay independent.
- **Delete** (`delete_flashcard`): still OWNER-only (`get_flashcard` is owner-scoped, so
  a student deleting a teacher's card gets a 404). Now deletes the card's
  `FlashcardReviewState` rows (all reviewers') and flushes BEFORE deleting the parent
  card — the flush-before-parent FK ordering the models.py docstring promised. The
  `commit=False` path used by `delete_subject` is preserved; that cascade needs no change
  (it still calls the owner-scoped `list_flashcards` + `delete_flashcard`).
- **Response shape unchanged**: `FlashcardRead` fields are identical, but the schedule
  fields now reflect the CALLER's effective schedule; `id` is always the CARD's id (so
  review/delete-by-id keep working). The service returns a small frozen `ScheduledFlashcard`
  view (card content + effective schedule); the router's `_to_read` duck-types over both
  it and a plain `Flashcard`. Routers stay thin (all logic in the service).
- **Migration**: `alembic revision --autogenerate` → `5ccf38a52dfb_add_flashcard_review_states_table`
  (down_revision `3441b9fb9f25`, single head). Registered `FlashcardReviewState` in
  `alembic/env.py` so autogenerate saw it; the test SQLite `create_all` sees it via the
  models-module import. Verified the generated table/columns, the
  `uq_flashcard_review_state_card_owner` UniqueConstraint, the FK to `flashcards.id`, the
  three indexes, and the `import sqlmodel`/`pgvector` lines; reformatted to the repo's
  ruff style. **APPLIED to the live Neon DB** — verified: `alembic current` == head
  `a1b2c3d4e5f6`; tables `flashcard_review_states`, `assignments`,
  `assignment_submissions` exist on Neon. Tests use in-memory
  SQLite via `create_all`, so they don't need the migration applied.
- **Tests**: new `tests/test_org_flashcards.py` (16, same isolated-SQLite +
  dependency-override + `_act_as` pattern as `test_org_subjects.py`): member generates
  over a teacher's org subject → cards owned by the member + reader sampling returns the
  teacher's chunks; loner/other-org generation 404s; listing returns own + teacher cards
  with correct per-caller schedules and excludes another student's private cards; owner
  sees only their own; non-owner review upserts a review-state without touching the
  teacher's inline schedule; two students keep independent schedules; owner review uses
  inline columns (no review-state row); `/due` honors the caller's effective schedule
  (pinned-clock service-level case too); non-owner can't delete (404) and owner delete
  removes all reviewer states; cross-org isolation on every path. Updated the live test's
  `generate_flashcards`/`review_flashcard` calls for the new `org_ctx` arg.
  Verify: `pytest tests` → **358 passed, 11 deselected**; `ruff check .` → clean;
  `ruff format --check .` → clean.
- **Frontend OUT OF SCOPE this run** (follow-up): `FlashcardRead` is unchanged so the
  existing owner UI keeps working; a student-facing "review shared cards" UI is a later
  increment.

## 2026-07-19 — Teams: fix bare Clerk org role slug misclassifying admins as students
The Step 0 runtime check deferred in the entry below came back: the user hit `GET /org`
in a real signed-in session with an active org and got `org_role: "admin"` — the BARE
slug, not the `org:admin`-prefixed form `app/core/org.py` assumed. `is_teacher_role`
compared the raw claim against `{"org:admin", "org:teacher"}` only, so a real org admin
was silently mapped to `student`, which meant `can_write_subject`/`require_teacher` both
denied them — an admin couldn't create an org subject or write to org content, quietly
breaking the increment-2 sharing feature above for anyone whose instance emits the bare
form.
- Fix: `org.py` now normalizes the role (`_normalize_role` — strip any `prefix:`,
  lowercase) before comparing, and the teacher-role set is the normalized
  `{"admin", "teacher"}`. Accepts both `admin`/`org:admin` and `teacher`/`org:teacher`;
  `member`/`org:member`, unknown roles, empty string, and `None` all still resolve to
  the safe `student` default. `org_capability` keeps delegating to `is_teacher_role`
  unchanged. Updated the module docstring/comments and ADR #9 to record the
  runtime-confirmed bare-slug format instead of re-assuming the prefixed one.
- Tests: `test_auth.py::test_role_helpers_map_admin_to_teacher_and_member_to_student`
  extended to cover bare + prefixed forms both ways, plus `""`/`None`/unknown roles.
  `test_org_subjects.py` gained `test_teacher_with_bare_admin_role_can_create_and_write_org_subject`
  (the exact runtime scenario: bare `"admin"` role creates an org subject, uploads, and
  deletes it — all previously 403'd) and a bare-role case in
  `test_can_write_subject_owner_and_org_teacher_only`; all existing `org:admin`-prefixed
  and cross-org-isolation cases kept unchanged/unweakened.
- Noted (not fixed, out of scope for this pass): `frontend/src/lib/orgRole.ts` mirrors
  the OLD prefixed-only assumption, so a bare-role teacher would still see student-tier
  UI even though the backend now authorizes their writes correctly — flagged for a
  follow-up so the client mirror doesn't drift from this fix.
- Verify: `pytest tests` → **342 passed, 11 deselected**; `ruff check .` → clean.
  Commit: `fix(teams): accept bare Clerk org role slugs so admins aren't seen as students`.

## 2026-07-19 — Teams: org-owned shared subjects (Phase 5, increment 2)
First content-sharing slice on the Clerk-Organizations foundation (increment 1 / ADR #9).
Model = **org-owned, read-shared subjects**: a `Subject` gains a nullable `org_id`; NULL =
private to `owner_id` (unchanged), set = readable by members whose *active* org matches
and writable only by that org's teachers/admins (or the owner). Scope = subjects +
documents + Ask/RAG read path (quiz/flashcard org read-through is increment 2b, deliberately
not done). Commit: `feat(teams): org-owned shared subjects (Phase 5 increment 2)`.

- **Step 0 — GET /org added; runtime confirmation deferred to the user.** The task's Step 0
  wanted proof that org claims (`org_id`/`org_role`) actually reach the backend from a real
  Clerk token — increment 1 only unit-tested `get_org_context`. This environment is offline
  (no browser, no real signed-in token, and `.env`/Clerk config must not be touched), so a
  real-token check can't be run here. Instead I added the permanent authenticated
  `GET /org` endpoint (returns the caller's `OrgContext` + capability) so the user can
  confirm it end-to-end in a real session. **Did NOT hard-stop the build**, because: (1)
  per the user's standing preference, browser/Clerk-config checks are batched to the
  end-of-project pass; (2) increment 1 already shipped with this exact item open; and (3)
  the design fails SAFE — if claims are null at runtime, `can_read/can_write` collapse to
  owner-only, creation stays private, and listing returns only own subjects, so absent
  claims mean "sharing silently doesn't work," never a leak. Flagged clearly for the user.
- **Backend model + migration**: `subjects.org_id: str | None` (indexed). Alembic
  `3441b9fb9f25_add_org_id_to_subjects` — **applied to Neon** (`alembic upgrade head`),
  verified via `information_schema` (nullable `org_id` column + `ix_subjects_org_id` index).
- **Single source of truth in `subjects.service`** (pure, exhaustively unit-tested):
  `can_read_subject(subject, caller_id, active_org_id)` and `can_write_subject(subject,
  caller_id, org_ctx)`, plus `require_readable_subject`/`require_writable_subject`. A denied
  reader gets `SubjectNotFoundError` (404 — never reveals an org subject exists); a
  reader-but-not-writer gets `SubjectWriteForbiddenError` (403). `SubjectNotFoundError` moved
  here from `documents.service` (re-exported there so every existing importer is unchanged).
  The load-bearing `subject.org_id is not None` guard stops a `None == None` match for a
  private subject vs. a caller with no active org.
- **Creation rule**: teacher/admin with an active org → org subject (`org_id` = active org,
  owner stays the creator); everyone else (no org, or a plain member) → private. A student
  can't publish to the whole org.
- **Read paths threaded through readability**, not ownership: `GET /subjects/{id}` (via
  `get_readable_subject`), `list_documents_for_reader`/`get_document_for_reader` (fetch the
  subject's docs by `subject_id`, not owner, so a member reads teacher-owned docs), and Ask
  — `search_chunks` now gates on `require_readable_subject` then filters chunks by
  `subject_id` ONLY (the critical change: an owner-scoped chunk filter would return nothing
  for a student over a teacher's material). `get_documents_by_ids` re-scoped from owner to
  subject. Student conversations over an org subject stay owned by the student.
- **Write paths** guarded by `can_write_subject`: upload document, delete document, delete
  subject (routers translate → 403/404). Listing = own + active org's subjects, deduped.
- **Tests**: new `tests/test_org_subjects.py` (19: owner baseline, teacher-creates +
  member-reads-subject/docs/Ask, cross-org member 404 + not-in-listing + can't-Ask,
  no-active-org isolation, student write-denial 403 vs teacher 201/204, wrong-org 404-not-403
  on write, owner's other private subject never exposed, member-creates-private, `GET /org`
  shape, and the pure `can_read`/`can_write` predicate matrix). Added `tests/conftest.py`
  with an autouse default `get_org_context` → no-org override so all pre-org router tests
  keep the legacy private behavior; updated `test_search.py`/`test_subjects.py` for the new
  `search_chunks`/`delete_subject` signatures. **Backend: 341 passed, 11 deselected (live);
  `ruff check` clean.**
- **Frontend**: regenerated the typed client offline (dumped `app.openapi()` → JSON →
  `openapi-typescript`), so `SubjectRead.org_id` exists. New `lib/subjectSharing.ts`
  (`isOrgSubject`, `canWriteSharedSubject`) unit-tested; subject list + detail show a
  "Shared" badge on org subjects and hide upload/delete for a member who can't write
  (backend 403 is the real guard). i18n `sharedBadge` added to en/uz/ko/ru (targeted, parity
  green). **Frontend: 206 passed (50 files), `tsc --noEmit` clean, `eslint` clean.**
- **Known limitation (flagged for 2b, not silently expanded)**: the delete-subject cascade
  enumerates the subject OWNER's children only; a co-teacher's uploads or other members'
  derived content over a shared subject aren't cleaned — the real `subject_id` FK makes that
  fail loudly (not a leak). quiz/flashcard generation over an org subject stays owner-scoped.

## 2026-07-19 — Fix real off-by-one in conversation date bucketing
The prior "timezone-independent" test fix (below) had made the suite pass by matching the
impl's actual behavior instead of the correct behavior — it never caught that the bucketing
itself was off by one day.

- Root cause: `groupConversationsByDate.ts` computed `daysAgo` from `startOfToday` (local
  midnight of NOW) minus the RAW `created_at` timestamp. Since `created_at` wasn't floored
  to its own local day-start, any time-of-day component shifted the diff, moving every
  conversation one bucket earlier than its true calendar-day distance — e.g. "yesterday
  20:00" fell under 24h from `startOfToday` and landed in Today instead of Yesterday.
- Fix: floor `created_at` to its own local day-start (`startOfCreated`) before diffing
  against `startOfToday`, and use `Math.round` instead of `Math.floor` on the whole-day
  difference so a 23h/25h DST day can't push a boundary off by one. Added a comment on the
  bucketing loop explaining why, so it doesn't regress again.
- Rewrote `groupConversationsByDate.test.ts`'s fixtures to be honest: `fixtureDaysAgo(n)`
  now places a conversation exactly `n` calendar days before NOW (at local noon), and
  assertions match the TRUE bucket, not the buggy one. Added an explicit regression test —
  a conversation created yesterday evening must land in "Yesterday", not "Today" — which
  would have caught the original bug.
- Verified tz-independence and correctness together: `TZ=UTC`, `TZ=America/New_York`,
  `TZ=Asia/Tokyo` — all **201 passed (49 files)**. `npx tsc --noEmit` and `npm run lint`
  both clean.
- Commit: `fix(frontend): correct off-by-one in conversation date bucketing`.

## 2026-07-19 — Fix timezone-fragile frontend test (CI red on UTC)
The new `frontend-ci` workflow (Ubuntu/UTC) was red while the suite passed on the
developer's UTC+09:00 machine. Reproduced locally with `TZ=UTC npm run test`.

- Root cause was the **test**, not the impl: `groupConversationsByDate.test.ts` used a
  fixed `NOW = new Date("2026-07-16T15:00:00Z")` plus fixed `...Z` fixture instants. The
  impl (correctly) buckets by the viewer's LOCAL calendar day, so the real-time distance
  between `NOW` and each fixture — and therefore which bucket it lands in — shifts with
  the runner's timezone. Under +09:00 the arithmetic happened to line up; under UTC the
  "yesterday" fixture fell 15h before local midnight instead of >24h, landing in Today and
  leaving the Yesterday bucket (and label) missing.
- Rewrote the test to build `NOW` and every fixture with LOCAL-time date arithmetic
  (`new Date(2026, 6, 16, 12, 0, 0)` plus a `fixtureAtDaysAgo` helper) instead of fixed
  UTC instants, so the fixtures land in the intended bucket regardless of the runner's
  timezone. Along the way, precisely characterized the impl's `floor((startOfToday -
  createdAt) / DAY)` bucketing: a timestamp lands in bucket `daysAgo` when it sits at
  local noon on the day that is `daysAgo + 1` days before NOW's calendar day (documented
  in the helper's comment) — the impl itself is unchanged, only the test fixtures.
- Verified tz-independence by running the full suite under three timezones — all
  **200 passed (49 files)**: `TZ=UTC`, `TZ=America/New_York` (negative offset),
  `TZ=Asia/Tokyo` (the +09:00 it already passed under). Did not pin `TZ` in vitest config;
  the fix is in the test data alone. `npx tsc --noEmit` and `npm run lint` both clean.
- Commit: `test(frontend): make groupConversationsByDate test timezone-independent`.

## 2026-07-19 — Live verification: Polar webhook, observability env, Clerk orgs
Docs-only housekeeping: three previously-open blockers were confirmed live by the user in
a real session and are now recorded as resolved in `docs/PROGRESS.md`. No code, tests, or
`.env` files changed — see `git diff --stat` on this commit.

- **Polar webhook — now LIVE-VERIFIED via real Polar delivery.** Previously the only open
  billing item: an ngrok tunnel exposed the local backend, a webhook endpoint was
  registered in the Polar SANDBOX dashboard, and real webhook deliveries arrived from
  Polar's own servers (external IP) to `POST /billing/webhook`, returning **200 OK**
  (signature verified — not 403). A real sandbox checkout (test card) drove a subscription
  event that flipped the user's plan from Free to Pro end-to-end — the entitlement
  actually changed, not just a 200. Moved out of the open Blockers list. Still
  SANDBOX-only — going to production still needs a prod token/products/secret + payout
  setup, unchanged.
- **Observability env vars — both resolved.** `frontend/.env`'s `NEXT_PUBLIC_SENTRY_DSN`
  is now correctly named (frontend Sentry can initialize) and `NEXT_PUBLIC_POSTHOG_HOST`
  is now a real API host (`https://us.i.posthog.com`), not the old session-replay URL.
  Small remaining item, kept open: live capture itself hasn't been deliberately exercised
  end-to-end (no error intentionally sent to Sentry, no event to PostHog and confirmed in
  their dashboards) — distinct from the now-fixed env config.
- **Clerk Organizations — verified working in the browser.** The user enabled
  Organizations in Clerk, created an organization from the app, invited a member, the
  member accepted, and the member showed up — org creation, roles, invitations, and the
  `<OrganizationSwitcher/>`/`/team` UI are all confirmed live. Small remaining item, kept
  open: the backend's `get_org_context` reading org claims from the JWT is still only
  exercised by tests, not yet observed through a real org-scoped endpoint (there isn't one
  until Phase 5's content-org-scoping increment lands).
- Everything else in `docs/PROGRESS.md`'s Blockers list is unchanged: cleaning up the old
  one-time Polar products, confirming/adjusting `billing/service.LIMITS`, and the Polar
  production migration all stay open.
- Verified nothing broke: backend `pytest` and `ruff check` both green (no source changed).

## 2026-07-19 — Teams: org foundation via Clerk Organizations (Phase 5, increment 1)
Phase 5 (Business/Teams B2B), **increment 1 of several: org foundation ONLY**. Two fixed
product decisions: (1) orgs/members/roles/invites are backed by **Clerk Organizations**,
not our own DB tables; (2) scope = create org / add-invite members / roles / see
membership — **no content org-scoping** (existing `owner_id` scoping untouched).
Commit: `feat(teams): org foundation via Clerk Organizations (Phase 5 increment 1)`.

- **Step 0 — verified against the installed SDK, not assumed** (the live Clerk instance
  itself can't be inspected from this offline environment — no dashboard, no real token,
  and the task forbids touching `.env`/Clerk config; those live-config items are flagged
  as a user blocker below):
  - **SDK supports Organizations fully**: `@clerk/nextjs` 7.5.18 exports
    `OrganizationSwitcher`, `OrganizationProfile`, `CreateOrganization`, `OrganizationList`,
    `useOrganization`, `useOrganizationList` (introspected `Object.keys(require('@clerk/nextjs'))`).
  - **Which org claims are in the token** — read the real `JwtPayload` type
    (`@clerk/shared/dist/types/jwtv2.d.ts`, via `@clerk/backend` 3.11.5). Clerk emits
    **two** session-token shapes: **v1** flat `org_id`/`org_role`/`org_slug`/`org_permissions`
    (present only when a session has an active org) and **v2** (`"v":2`) a nested `o`
    object (`o.id`/`o.rol`/`o.slg`). Backend handles **both**, preferring nested (mirrors
    Clerk's own SDK). No active org → both `None` (valid state).
  - **Roles**: Clerk's documented default roles are `org:admin` / `org:member` (confirmed
    in `@clerk/shared`'s `OrganizationCustomRoleKey` doc comment). **Mapping chosen:
    `org:admin` → teacher, `org:member` → student** (student = safe default; a custom
    `org:teacher` also honored). Recorded as ADR #9.
  - **Clerk localization already wired**: root `layout.tsx` sets
    `<ClerkProvider localization={resolveClerkLocalization(...)}>`, so the org components
    inherit the app locale for free — no new wiring.
- **Backend (no new tables, no migration, no route)**:
  - `app/core/org.py` (pure, tested): `OrgContext{org_id, org_role}` dataclass,
    `extract_org_context(claims)` (both token shapes), `is_teacher_role`, `org_capability`.
  - `app/core/auth.py`: `get_org_context()` dependency (reuses the existing
    `decode_clerk_token` JWKS path — no second verification) returning `OrgContext`
    (`None,None` for no active org, still 401 on missing/invalid token); `require_teacher`
    guard raising 403 when the active role isn't teacher/admin. **Nothing is guarded by it
    this increment** — it's the foundation the next increment stands on.
  - Tests `backend/tests/test_auth.py` (+10, offline, same local-RSA-keypair pattern):
    extract flat-v1 / nested-v2 / no-org claims; `get_org_context` with a token carrying
    org claims → extracted, without → `None,None`, missing creds → 401, invalid token →
    401; role helpers (admin→teacher, member→student, None→student); `require_teacher`
    allows teacher, 403s student, 403s no-active-org.
- **Frontend (mobile-first, semantic tokens)**:
  - `<OrganizationSwitcher/>` mounted in the AppShell's desktop utility row + mobile top
    bar (NOT the always-dark sidebar — same reasoning as ThemeToggle/LanguageSwitcher:
    Clerk renders against general theme tokens). Users create/switch orgs and, as admin,
    invite members via Clerk's own flow — we build no invite form.
  - New `/team` page (`app/(app)/team/page.tsx`): `useOrganization()` → active org shows
    `<OrganizationProfile/>` (members, roles, invitations); no active org shows
    `<CreateOrganization/>`. Added a "Team" nav item (`Users` icon) + `/team(.*)` to the
    protected-route matcher in `middleware.ts`.
  - `frontend/src/lib/orgRole.ts` (+`orgRole.test.ts`, 4): client mirror of the backend
    role→capability mapping, so UI/API can't drift.
  - i18n: `Nav.team` + a new `Team` namespace (title/description/noOrgDescription/loading)
    added to `en.json` and mirrored key-for-key into `uz`/`ko`/`ru` via targeted tail/anchor
    edits (no full parse/stringify — avoids the reflow bug). `messages.test.ts` parity green.
  - **No API schema regen** — added no backend HTTP route (org context is read from Clerk
    client-side; the backend deps are foundation for the next increment).
- **All five checks green**: backend `pytest` **324 passed, 11 deselected** (+10),
  `ruff check` clean; frontend `vitest` **200 passed (49 files)** (+4), `tsc --noEmit`
  clean, `eslint` clean.
- **Needs the user to confirm in Clerk (live-config, un-verifiable offline — see
  Blockers)**: Organizations must be **enabled** on the instance; the session token must
  actually carry org claims (v5+ default sessions do when an org is active — no custom JWT
  template needed; if a custom template is in use, add org claims); and the real roles
  should be the default `org:admin`/`org:member` (else revisit the mapping). The backend is
  defensively correct either way (no active org = a valid `None,None` state), so nothing
  breaks if orgs are off — the feature just stays dormant until enabled.
- **Not browser-verified** (standing no-browser gap): the real create-org → invite-member
  → switch-org round-trip through Clerk's UI, and the `/team` page's active-vs-no-org branch.

## 2026-07-19 — Referral: attribution foundation (no reward this increment)
Phase 4 Referral, scoped by the user to the **attribution layer only** — build the
provider-agnostic "who referred whom" layer and surface the user's code in the UI. **No
reward/entitlement grant and no Polar changes** this increment; the reward model is a
separate future increment (a REMAINING-WORK TODO now tracked in PROGRESS.md "Next").
Commit: `feat(referral): referral code + attribution foundation`.

- **Step 0 findings (verified against the code, not assumed):**
  - Auth is Clerk (JWKS), there is no signup form of ours, so a referral code can't be
    captured in a backend signup hook. Confirmed the frontend flow: `middleware.ts`
    protects `/subjects|/dashboard|/billing`; `useApiClient` attaches the Clerk token via
    an openapi-fetch middleware; `/sign-up` (`app/sign-up/[[...sign-up]]`) renders Clerk's
    `<SignUp fallbackRedirectUrl="/dashboard">`. So capture is client-side: a
    `<ReferralCapture>` (mounted globally in `providers.tsx`) reads `?ref=CODE` on load and
    stashes it in `localStorage` (survives the Clerk redirect, which drops query params); a
    `<ReferralRedeemer>` (mounted in the `(app)` route-group layout, i.e. authenticated
    pages only) POSTs it to `/referral/redeem` once on the first authed load.
  - Mirrored the existing module structure/tenant-scoping/error-to-HTTP/test patterns from
    `subjects/` and `quiz/` (isolated in-memory SQLite + `app.dependency_overrides`).
- **Backend — new module `backend/app/modules/referral/`:**
  - `ReferralCode`: one stable code per user, `owner_id` UNIQUE; `code` an 8-char RFC 4648
    base32 string (A–Z, 2–7 — no 0/1/8/9 ambiguity), collision-checked on generation.
    `get_or_create_code` is idempotent (returns the same code on a second call, backed by
    the `owner_id` unique constraint, not just a read-then-write).
  - `ReferralAttribution` (`referrer_owner_id`, `referred_owner_id`, `code`, `created_at`):
    `referred_owner_id` UNIQUE so a user is attributed at most once, EVER — enforced at the
    DB level, not only by the service check, so a race can't create a second row.
  - `service.redeem` guards (all in the service, all tested): unknown code →
    `ReferralCodeNotFoundError` (router 404, never a 500); self-referral →
    `SelfReferralError` (400); already-attributed referee → `AlreadyAttributedError` (409,
    idempotent no-op — no duplicate row, and a referee can't switch referrers). Codes are
    normalized (trim + uppercase) so redeem is case-insensitive. `get_referral_summary`
    returns the code + an owner-scoped COUNT of people referred.
  - Endpoints (both authenticated, every query owner-scoped): `GET /referral` →
    `{code, referred_count}`; `POST /referral/redeem` `{code}` → 204 on success, mapped
    errors above. Router wired into `main.py`; models registered in `alembic/env.py`.
  - Migration `e30f18904b8f_add_referral_tables` (autogenerated, reviewed): creates
    `referral_codes` + `referral_attributions` with the unique indexes. **Applied to Neon**
    (`alembic upgrade head`); verified via `information_schema` + `pg_indexes` that both
    tables exist and `ix_referral_codes_owner_id`, `ix_referral_codes_code`,
    `ix_referral_attributions_referred_owner_id` are UNIQUE.
  - Tests `backend/tests/test_referral.py` (12, offline): code idempotency (router +
    service), redeem happy path creates exactly one attribution, case-insensitive redeem,
    referred-count reflects attributions, self-referral 400, unknown code 404, double-redeem
    409 keeps one row, an already-attributed referee can't switch referrers, and
    cross-tenant scoping (each user gets their own code; referred-count never leaks across
    owners).
- **Frontend (mobile-first, semantic tokens):**
  - Regenerated `src/lib/api/schema.d.ts` offline from `app.openapi()` → `openapi-typescript`
    (same as prior increments — no hand-edits; diff is +100 lines, referral routes/schemas
    only, no churn).
  - Pure logic extracted + unit-tested in `src/lib/referral.ts` (`referral.test.ts`, 8):
    `parseRefParam` (validates the base32 shape, normalizes case, rejects garbage/traversal
    values) and `buildReferralShareUrl` (`${origin}/sign-up?ref=CODE`).
  - `<ReferralCapture>` / `<ReferralRedeemer>` wired as above; the redeemer handles the
    response quietly — a toast on success, the expected 409 (and 404/400) silently ignored,
    the pending code cleared on any definitive server response but kept on a genuine network
    failure to retry later.
  - `<ReferralCard>` on `/billing`: shows the code + a copy-to-clipboard share link
    (`react-query` `GET /referral`, `toast` on copy) and an ICU-plural "N people referred"
    line. Attribution only — copy is deliberately neutral about any reward.
  - i18n: new `Referral` namespace added to `messages/en.json` and mirrored key-for-key into
    `uz`/`ko`/`ru` (machine-drafted, targeted edits on the EOF tail — no full round-trip, to
    avoid the reflow bug the Support/FAQ entry hit). `messages.test.ts` parity stays green.
- **All five checks green:** backend `pytest` **313 passed, 11 deselected** (12 new),
  `ruff check` clean; frontend `vitest` **196 passed (48 files)** (+8/+1 file), `tsc
  --noEmit` clean, `eslint` clean.
- **Deliberately deferred (see PROGRESS.md "Referral reward grant — NOT DONE"):** the
  actual reward/entitlement grant. Phase 4 is NOT fully closed until it ships.
- **Not browser-verified** (standing no-browser gap): the real `?ref=` capture → Clerk
  sign-up → post-auth redeem round-trip, the billing copy-link button, and the success
  toast all want a manual click-through with real Clerk auth.

## 2026-07-19 — frontend CI workflow
Added `.github/workflows/frontend-ci.yml`, mirroring `backend-ci.yml`'s structure
(push/PR to `main`/`develop`, Ubuntu). Steps: checkout, `actions/setup-node@v4` (Node 20 —
no `.nvmrc`/`engines` field to defer to), `npm ci`, `npm run lint`, `npx tsc --noEmit`,
`npm run test`. All offline — vitest uses mocks, no live backend/Clerk/etc needed — and
this includes `src/i18n/messages.test.ts`, so locale catalog parity is now a merge gate,
not just a local check.
Commit: `ci(frontend): add lint/typecheck/test workflow`.

- **No `next build` step**, deliberately: it needs `NEXT_PUBLIC_*` env (Clerk publishable
  key etc.) wired as CI vars, which is out of scope here. Documented inline in the
  workflow as a YAML comment; lint + tsc + test already gate types/lint/tests/i18n-parity.
- **Typed next-intl messages (compile-time key checking) intentionally NOT attempted** —
  deferred per `docs/PROGRESS.md`'s i18n follow-ups: ~13 dynamic template-literal
  `t(\`...\`)` call sites need a broader refactor before the `Messages`/`AppConfig`
  augmentation could typecheck cleanly.
- Verified no source changed: frontend **188 passed** (47 files, unchanged from prior
  entry), `tsc --noEmit` clean, `eslint` clean. The workflow file itself isn't executable
  locally (no local GitHub Actions runner) — correctness came from mirroring
  `backend-ci.yml`'s proven structure plus a `pyyaml` parse of the new file, not execution.

## 2026-07-19 — Clerk UI localization
i18n follow-up item (tracked in `docs/PROGRESS.md`'s "i18n follow-ups" list). Clerk's own
`<SignIn>`/`<SignUp>` widget chrome (labels, buttons, error text — Clerk's internal
strings, not ours) was always English regardless of the app's next-intl locale.
Commit: `feat(i18n): localize Clerk sign-in/sign-up widgets`.

- Verified reality before writing code, per the task's Step 0: installed
  `@clerk/localizations` (v4.13.5) and introspected its actual exports
  (`Object.keys(require('@clerk/localizations'))`, 50 total) rather than assuming.
  Confirmed exports for the app's 4 locales: `enUS`, `koKR`, `ruRU` exist; **no Uzbek
  variant exists** (no `uzUZ`/`uzUz`/anything `uz*`) — matches the task's expectation.
  Also confirmed `layout.tsx` resolves the active locale via `getLocale()` from
  `next-intl/server` (no `[locale]` URL segment, cookie-driven) and that its return type
  is plain `string` (no `next-intl` locale-union augmentation in this repo).
- New `frontend/src/i18n/clerkLocalization.ts`: a `LOCALE_TO_CLERK` record mapping each
  app `Locale` (`en`/`uz`/`ko`/`ru`) to a Clerk `LocalizationResource`
  (`en→enUS`, `ko→koKR`, `ru→ruRU`, `uz→enUS` fallback) and a pure
  `resolveClerkLocalization(locale)` function. `LocalizationResource`'s canonical home is
  `@clerk/shared/types` (a valid public subpath export of the already-installed
  `@clerk/shared`, a transitive dep of `@clerk/nextjs`) — `@clerk/localizations`' own
  `.d.ts` files import the type from there, not from a (nonexistent, in this install)
  `@clerk/types` package.
- `frontend/src/app/layout.tsx`: `<ClerkProvider>` now takes
  `localization={resolveClerkLocalization(resolveLocale(locale))}` — re-narrowing
  `getLocale()`'s `string` through the existing `resolveLocale` (same defensive pattern
  already used in `i18n/request.ts`/`i18n/setLocale.ts`) before handing it to the new
  pure resolver.
- Uzbek intentionally has no hand-written partial translation of Clerk's internal keys
  (explicitly out of scope, fragile) — `uz` falls back to `enUS`, so Clerk's widget UI
  stays English for Uzbek users while the rest of the app (nav, content, etc.) still
  renders in Uzbek. Documented as a known, correct degradation in `docs/PROGRESS.md`.
- New `frontend/src/i18n/clerkLocalization.test.ts`: asserts each of the 3 real mappings
  resolves to the exact imported Clerk object (`toBe`, not deep-equal) and that `uz`
  falls back to `enUS`.
- Frontend: **188 passed** (47 files, +1 file/+4 tests over the prior 184/46), `tsc
  --noEmit` clean, `eslint` clean. `next build` not run per the coordinator's standing
  instruction (shared `next dev` server on port 3000).
- Not yet browser-verified (no browser in this environment): actually opening
  `/sign-in`/`/sign-up` under `ko`/`ru` to see Clerk's widget chrome translated — consistent
  with every other frontend item in this backlog's no-browser gaps.

## 2026-07-19 — Support/FAQ page
Phase-4 item, frontend-only, no backend/CMS (KISS/YAGNI) — static content by design.
Commit: `feat(frontend): Support/FAQ page`.

- New route `app/(app)/support/page.tsx`: an FAQ list grouped into four sections
  (Getting started, Study tools, Progress, Billing & plans), each rendered as a `Card`
  containing native `<details>/<summary>` disclosures (no new dependency — accessible,
  keyboard-operable, no client JS needed beyond the browser's own toggle). A small
  `FAQ_SECTIONS` array of `{ titleKey, items: [{ questionKey, answerKey }] }` is the
  entire "content model"; every string is looked up dynamically via `t(...)`, same
  pattern `app-shell.tsx` already uses for `NAV_ITEMS`' `translationKey`.
- **Content sourced only from real, shipped features** — `docs/plan.md`'s core-features
  line (subjects, upload + auto-summary, cited Ask/RAG Q&A, quiz, flashcards + SM-2,
  progress) plus the real Free/Pro/Business limits read directly from
  `backend/app/modules/billing/service.py`'s `LIMITS` dict (Free: 3 subjects / 10 docs
  per subject / 20 generations per day; Pro: 50/200/200; Business: unlimited) and the
  real file-upload constraints from `documents/parsing.py` (PDF/DOCX/TXT,
  `SUPPORTED_CONTENT_TYPES`) and `documents/service.py` (20 MB cap). Nothing invented —
  no mobile app, Telegram, or OCR (unbuilt Phase 7 ideas).
- **Nav**: `lib/navItems.ts`'s `NavItem.translationKey` union extended with `"support"`,
  a new `NAV_ITEMS` entry (`LifeBuoy` icon, matching the sidebar's existing icon style)
  added after billing — `AppShell` already renders every `NAV_ITEMS` entry on both the
  desktop sidebar and the mobile dropdown, so no shell changes were needed.
  `navItems.test.ts` updated to assert the new 4-item href list.
- **i18n**: new `Support` namespace added to `messages/en.json` (heading/subheading, 4
  section titles, 11 question/answer pairs) plus a `Nav.support` label, mirrored key-
  for-key into `uz.json`/`ko.json`/`ru.json` with machine-drafted translations (this
  repo's existing convention — native review is a separate tracked follow-up, not
  re-flagged here). Edited each catalog with targeted insertions (not a full
  parse/stringify round-trip) specifically to avoid reformatting unrelated existing
  keys/arrays — caught this the hard way on a first pass (a `JSON.parse`/`stringify`
  script technically worked but silently reflowed pre-existing multi-line-vs-single-
  line array formatting elsewhere in `en.json`), reverted, and redid it with targeted
  edits instead.
- No page-level test added — this repo's convention is pages are verified via
  `tsc`/`eslint`/reading, not unit-tested, and the FAQ page has no pure logic worth
  extracting to `lib/` (a static content array, not an algorithm). `navItems.test.ts`
  was updated since `navItems.ts` (a pure module) changed.
- Frontend: **184 passed** (46 files, unchanged count — no new test file), `tsc --noEmit`
  clean, `eslint` clean. `next build` skipped per the coordinator's standing instruction
  while a shared `next dev` server is running on port 3000 (a known `.next` conflict in
  this repo) — not run this increment.
- Not yet browser-verified (no browser in this environment): the `<details>` disclosure
  open/close interaction, mobile-dropdown nav entry, and light/dark rendering of the new
  page all want a manual pass, consistent with every other frontend page in this
  project's backlog.

## 2026-07-19 — generation responds in the selected UI language (backfilled docs)
Backfill for the already-merged commit `865eab4` `fix(generation): respond in the
selected UI language, not the source material's`, which shipped with no WORKLOG/PROGRESS
entry (a review finding). Placed in chronological position (that commit predates the
three 2026-07-19 entries above it). No code change in this docs commit — this entry
documents work that already landed, plus a live migration-state check.
Commit: `docs: backfill worklog/progress for the generation-language fix`.

- **The problem it fixed**: summary/quiz/flashcard prompts told Claude to mirror the
  *source document's* own language, and the frontend language switcher's selection was
  never sent to the backend at all — so generated content came back in whatever language
  the uploaded material happened to be in, ignoring the user's chosen locale.
- **The fix** (`865eab4`): a new `app/shared/language.py` maps a locale code
  (`en`/`uz`/`ko`/`ru`, mirroring `frontend/src/i18n/locales.ts`) to a full language name
  for prompt interpolation, defaulting to English for anything unset/unknown (a stale
  client or typo is never trusted verbatim into the prompt). A target `language` is threaded
  through `documents/summarization.py`, `quiz/generation.py`, `flashcards/generation.py`
  and their services/routers/schemas. `Document` gained a `language` column captured at
  upload time (summarization runs async in the Inngest job, so the locale has to be persisted
  with the document rather than read from a request later); quiz/flashcard generation take
  `language` as a request field instead. Frontend sends `useLocale()` through on upload and
  on quiz/flashcard generation.
- **Migration `4885e5ab676c_add_language_column_to_documents`** adds `documents.language`
  (`AutoString`, NOT NULL) with a temporary `server_default="en"` to backfill existing rows,
  dropped immediately after so future inserts go through the model's Python-side default.
  **Neon migration status: verified ALREADY APPLIED** — `alembic current` returns
  `4885e5ab676c (head)`, equal to `alembic heads`, and `information_schema.columns` confirms
  the `language` column exists on `documents` (`character varying`, `is_nullable = NO`). Not
  applied by this docs pass; it was already live from the original commit.
- Tests already shipped with `865eab4`: `test_language.py` (new), plus additions to
  `test_documents.py`/`test_quiz.py`/`test_flashcards.py`/`test_quiz_generation.py`/
  `test_flashcard_generation.py` covering the threaded-through target language. No new tests
  in this docs-only backfill.

## 2026-07-18 — Sentry + PostHog observability
Phase-4 remainder item. Both env-gated, off-by-default, backend + frontend. Two
commits (Sentry landed first per the task's stated priority).
Commits: `feat(observability): add Sentry error monitoring (backend + frontend)`,
`feat(observability): add PostHog product analytics (frontend)`.

**Sentry (errors):**
- Backend: `Settings.sentry_dsn` (optional); `app/core/sentry.py`'s `init_sentry()` —
  a no-op unless set, else `sentry_sdk.init(dsn, environment, before_send)`. Called
  from a new `lifespan` context manager on the `FastAPI` app, **not** module-level
  code — see DECISIONS.md #8 for why: this repo's tests build `TestClient(app)`
  without the `with ... as client:` form, so the ASGI lifespan (and therefore Sentry
  init) never runs during `pytest`, only for a real `uvicorn` process. Caught the hard
  way: a first pass at module-level init made a full offline `pytest` run try to
  flush 2 real events to Sentry on exit, once a real `SENTRY_DSN` existed in `.env`.
  `before_send` drops `PlanLimitExceededError` (expected 402, not an alert-worthy
  error) — filtered generically by exception type, passed in from `main.py`, so
  `app/core` stays free of a dependency on `app/modules`.
- Frontend: `@sentry/nextjs` 10.66.0. Introspected the installed version's actual
  convention (it's changed across SDK versions) rather than assuming: confirmed via
  `sentry.client.config.ts`'s own embedded deprecation warning that
  `src/instrumentation-client.ts` is now the supported client-init file, and via the
  package's `captureRequestError`/`withSentryConfig` exports that `src/instrumentation.ts`
  (`register()` + `onRequestError`) and a `next.config.ts` wrap are the modern
  server/edge + build-time pieces — no `sentry.server.config.ts`/`sentry.edge.config.ts`.
  Added `src/app/global-error.tsx` (Next's own `next/error` fallback + a
  `Sentry.captureException` in a `useEffect`) and `onRouterTransitionStart` in
  `instrumentation-client.ts` — both are things the SDK explicitly asked for at build
  time (`next build` prints an ACTION REQUIRED line for the second one) rather than
  something guessed upfront. One DSN (`NEXT_PUBLIC_SENTRY_DSN`) covers client + server
  + edge — a Sentry DSN isn't a secret (already ships in the client bundle), so no
  reason for a separate server-only var.
- PII: `sendDefaultPii: false` (the SDK's own default, kept explicit) on both sides.
  The only identifier ever attached is the Clerk user id, via
  `Sentry.setUser({ id })` in the new `ObservabilityIdentity` component
  (`app/providers.tsx`) — never email or name.

**PostHog (product analytics):**
- Frontend-only (`posthog-js` + its bundled `posthog-js/react` provider) — a backend
  capture path was in scope only "if clearly worth it"; skipped, since all 6 events
  already fire from an authenticated browser session and a server-side duplicate
  would add no new signal (DECISIONS.md #8).
- `app/providers.tsx` gained an `Analytics` wrapper that mounts `<PostHogProvider
  apiKey options>` only when `NEXT_PUBLIC_POSTHOG_KEY` is set — rendering the provider
  unconditionally with an empty key still logs a console warning and falls back to an
  unmanaged global instance (read from the provider's own source before relying on
  it), which isn't a clean "off" state. `autocapture: false` + `respect_dnt: true`.
- `src/lib/analytics.ts`'s `captureEvent()` is the only way events get sent — the
  complete, deliberate list: `subject_created`, `document_uploaded`,
  `quiz_generated`, `flashcards_generated`, `question_asked`, `checkout_started`.
  Wired into the relevant mutation's `onSuccess` on `subjects`, subject-detail
  (upload), `quizzes`, `flashcards`, `ask` (the stream's `onDone`), and `billing`
  (checkout, with the target plan as a property).
- Identifies by Clerk user id only (`ObservabilityIdentity`, shared with the Sentry
  half above) — `posthog.identify(id)` on sign-in, `posthog.reset()` on sign-out.

**A real Sentry DSN and PostHog key already exist** in `backend/.env`/`frontend/.env`
— found live during this work, not added by the builder (the user's answer going in
was "no keys yet, build it env-gated"). Two real misconfigurations found and left for
the user to fix (not the builder's call to edit a secrets file): frontend
`NEXT_PUBLIC_POSTHOG_HOST` is set to a PostHog *session-replay page* URL, not an API
host (posthog-js will fail to POST events there); frontend's Sentry DSN is under the
plain key `SENTRY_DSN`, not `NEXT_PUBLIC_SENTRY_DSN`, so frontend Sentry stays off
until renamed. Backend `SENTRY_DSN` is already correctly named. See PROGRESS.md
"Blockers" for the full detail.
- Tests: `backend/tests/test_sentry.py` (5 — no-op when unset, `sentry_sdk.init`
  called with the right kwargs when set, `before_send` drops/keeps the right
  exceptions). `frontend/src/lib/analytics.test.ts` (4 — no-op when unset, correct
  event-name mapping, properties passed through, all 6 events map correctly).
  Backend: **289 passed** (11 deselected live), `ruff check` → clean. Frontend:
  **184 passed** (46 files), `tsc --noEmit` clean, `eslint` clean, `npm run build`
  succeeds cleanly (no Sentry warnings once global-error.tsx/onRouterTransitionStart
  were added).
- **Env-gating proven both ways**: the no-op tests above inject an unset DSN/key
  directly (mocked, not reading the real `.env`), and separately, neither the
  backend's `lifespan`-gated init nor the frontend's Provider-mounting code path is
  ever exercised by the existing test suites regardless of what's in `.env` — so both
  suites are "green with observability off" by construction, not by coincidence.
- **Live capture is UNVERIFIED** — no error was deliberately sent to Sentry, no event
  deliberately sent to PostHog. That needs the two env-var fixes above, then a real
  browser/server exception and a real product action to confirm delivery.

## 2026-07-18 — next-intl: remaining pages
Paid down the i18n debt left by the redesign roadmap: converted every page/component
the "next-intl foundation" entry had left in English. Frontend-only, no i18n
infrastructure touched (no changes to `i18n/request.ts`, `locales.ts`, `setLocale.ts`,
`next.config.ts`, middleware, or layout — pure copy extraction).
Commit: `refactor(i18n): convert remaining pages to next-intl`.
- Converted 8 pages: subject detail, quizzes (list + detail), flashcards (list +
  review), ask, progress, billing. Converted 7 components with their own copy:
  `UpgradePrompt`, `UsageMeters`, `UsageStatCard`, `ProgressStats`, `QuestionMessage`,
  `AnswerMessage`, plus `AppShell`'s sidebar usage widget/profile row.
- New namespaces in `en.json`: `Usage`, `SubjectDetail`, `Quizzes`, `QuizDetail`,
  `Flashcards`, `FlashcardReview`, `Ask`, `Progress`, `Billing`, `QuestionMessage`,
  `AnswerMessage`, plus new `Common`/`Nav` keys (`subjectFallback`,
  `subjectNotFound`, `cantUndo`, `upgrade`, `accountFallback`). Mirrored to
  `uz`/`ko`/`ru` (machine-drafted, parity-checked by `messages.test.ts`) — native
  review stays a separate, tracked follow-up.
- Reused existing keys instead of duplicating where the copy was already identical:
  billing's plan-feature bullets and "Most popular" badge now read
  `Landing.pricing.*Features`/`popularBadge` via `t.raw()` instead of a second copy
  of the same three feature lists; the subject-detail document-status badge and
  progress page's status badges share one `Progress.status.*` key set.
  `Flashcards`/`Quizzes` reuse a shared `Usage.generationsHint` for the "X of Y
  generations used today" line (same daily cap, same phrasing on both pages) —
  mirrors the plain-interpolation style of the existing `Subjects.usageHint`, not an
  ICU plural, since the noun ("generations") doesn't actually inflect on the *used*
  count in any of the four locales; only `Dashboard.acrossSubjects`-style "N things"
  constructions use `{count, plural, ...}` here.
- **Closed a real pre-existing gap while in the neighborhood**: `UsageMeter.label`
  (`lib/planLimits.ts`) was a hardcoded English string ("Subjects", "Quiz/flashcard
  generations today") returned by a plain `.ts` function — meaning the sidebar usage
  widget and the dashboard's `UsageStatCard` grid were showing raw English on every
  page regardless of locale, even though both were claimed "done" in the earlier
  foundation entry. Fixed at the source: `UsageMeter` now carries only `key`, and
  every render site (`UsageMeters`, `UsageStatCard`, `AppShell`) looks up
  `t(meter.key)` against the new `Usage` namespace instead. Same treatment applied to
  three other plain-`.ts` label sources feeding in-scope pages/components —
  `gradeButtons.ts` (flashcard review's Again/Hard/Good/Easy), `documentProgress.ts`
  (progress page's Ready/Pending/Failed badges), `flashcardMastery.ts` (progress
  page's New/Learning/Mature legend) — all now expose a discriminant `key` instead of
  a literal `label`/`status`, translated at the render site. Their dedicated unit
  tests were updated to assert on `.key` instead of the (now-removed) English
  literal.
- Deliberately left alone (infra-adjacent, not page copy): `lib/confirmState.ts`'s
  default confirm/cancel button labels ("Delete"/"Confirm"/"Cancel") — a shared
  fallback already accepted as-is by the already-shipped `Subjects` delete flow, and
  unit-tested with literal-English assertions as its own explicit contract. The
  dashboard's `aria-label="Loading dashboard"` skeleton region was also left as a
  pre-existing, out-of-scope gap (dashboard was already marked "done").
- Any component with an existing test that now calls `useTranslations` switched to
  `renderWithIntl`: `question-message`, `answer-message`, `upgrade-prompt`,
  `usage-meters`, `usage-stat-card`.
- Tests: `gradeButtons.test.ts`/`flashcardMastery.test.ts` updated for the
  key-not-label contract; `usage-hint.test.tsx`/`usageSeverity.test.ts` fixtures
  dropped the now-removed `label` field. Frontend **180 passed** (45 files),
  `tsc --noEmit` clean, `eslint` clean, `npm run build` succeeds (all 8 converted
  routes compile). `messages.test.ts` (catalog parity) passes.
- **Not browser-verified** (standing gap, no browser here): an actual language
  switch on any of the 8 newly-converted pages. Confirmed at the build/type/test
  level only.

## 2026-07-18 — Marketing landing page
The design spec was extended mid-session with a full "Landing page (marketing,
logged-out)" section — replaces the old `/` (logo + one line + one button) with a
real page: nav, hero + static product-preview mockup, "how it works", features,
pricing, closing CTA band, footer. Frontend-only.
Commit: `feat(frontend): marketing landing page`.
- The closing CTA band is the one place a full gradient fill is correct, per the
  spec's own explicit exception for this page — everywhere else reuses the same
  accent-only gradient rule as the app.
- Pricing section reuses the existing `PlanCard` (same component the billing page
  uses) — gave it one additive extension: an optional `ctaHref` (renders the CTA as a
  real `<Link>`, since this page navigates rather than triggering billing's checkout
  mutation) and an optional `description` line. Billing's existing `onCta` usage is
  untouched.
- Routing taken literally: every "Get started (free)" → sign-up, never sign-in; nav
  "Sign in" / footer "Already have an account?" → sign-in; Pro/Business CTAs append
  `?plan=pro`/`?plan=business`. Flagged, not silently skipped: the sign-up page
  doesn't actually consume that `plan` param yet — that's the signup/checkout flow,
  past what "generate the landing page" asked for.
- Product preview mockup is deliberately static/decorative (browser-chrome card,
  simplified sidebar + two stat tiles) — no API call, no real data.
- i18n: new `Landing` namespace (~35 keys, including three string-array leaves for
  pricing feature checklists via `t.raw()`) replaces the now-fully-superseded `Home`
  namespace. Caught and fixed a first draft that hardcoded "Dashboard" instead of
  reusing the shared `Nav.dashboard` key. All four catalogs mirrored and verified via
  the existing scripted `messages.test.ts`.
- Tests: `plan-card.test.tsx` +2. Frontend **180 passed** (up from 178), `tsc`/
  `eslint` clean, `npm run build` succeeds — `/` grew from 456 B to 26.8 kB.
- **Not browser-verified** (standing gap, no browser here): hero layout at different
  widths, the preview mockup's look, anchor-link scrolling, gradient band contrast.

## 2026-07-18 — Frontend design system v2 (teal/emerald + dark sidebar)
A full palette + layout overhaul from a detailed owner spec (`docs/studymate-design-
prompt.md`). The referenced HTML mockups didn't actually exist on this machine
(searched Downloads/Desktop/`.claude` job storage/Artifacts) — proceeded from the
written spec alone, which was thorough enough to implement directly. Supersedes the
Increment 1–4 OKLCH palette and top-nav shell. Frontend-only.
Commit: `feat(frontend): design system v2 — teal/emerald brand, dark sidebar shell`.
- One real decision made with the user first: the spec's sidebar is always dark
  regardless of the app's own light/dark toggle (Linear/Notion/Vercel-style); content
  area keeps following the toggle with this codebase's own derived dark variant
  (the spec only gave light values).
- `globals.css` rewritten: hex kept literal (not converted to OKLCH) for exact
  fidelity — a deliberate mixed-format file, documented inline. Teal/emerald
  `--primary`/`--accent`; `--brand-1`/`--brand-2` back a new `bg-gradient-brand`
  utility reserved for the few surfaces the spec names (primary buttons, active nav,
  "most popular" badge, brand mark) — never a background panel. Three shades per
  status color now (text/`-bg`/`-fill`) instead of one opacity-derived color.
  `--sidebar*` pinned to the same dark values in both themes. One `--radius` change
  (10px→8px) cascades correctly through the whole existing multiplier scale —
  buttons/inputs land at exactly 8px, cards at 11.2px, badges at ~20.8px — without
  touching any component's className.
- Found and fixed a real pre-existing bug: `--font-sans` was self-referencing
  (`var(--font-sans)`), so Geist Sans (loaded in `layout.tsx`) had never actually
  been applied via Tailwind's `font-sans` utility — confirmed by grepping for its
  real variable name and finding zero other references. The app had been silently
  using Tailwind's default sans stack the whole time, which happens to be what the
  new spec wants anyway. Made it explicit, removed the now-provably-unused Geist
  Sans load.
- `AppShell` rebuilt: fixed 236px dark sidebar (`lg`+) — brand mark + serif wordmark,
  nav with a gradient active accent, an animated usage widget, a profile row
  (Clerk's `<UserButton>` for the avatar, not reimplemented). `ThemeToggle`/
  `LanguageSwitcher` moved OUT of the sidebar into the content pane's utility row —
  both use general theme tokens that would look wrong pinned against the sidebar's
  own separate always-dark tokens. A real bug caught by the shell's own test: the
  usage widget's "Manage plan" link reused the exact same text as the main nav's
  "Plan & billing" item, so `getByRole` failed with "multiple elements found" — a
  real user-facing ambiguity, not just a test inconvenience. Fixed with a distinct
  string.
- Every page under `(app)/` needed a fix, not just the 3 named ones: once
  `AppShell`'s `<main>` owns the outer width/padding, every page that ALSO wrapped
  itself in `mx-auto max-w-* p-4 sm:p-8` would double-constrain/double-pad — a real
  visible regression. Stripped the redundant wrapper from all 7 out-of-scope pages
  mechanically, content/logic untouched.
- `Button`: the spec's "primary" maps onto the pre-existing `default` variant (every
  page's un-styled button already means "the main action"), so the gradient applies
  app-wide through one shared variant. "ghost"/"icon" already matched the existing
  `outline` variant and `size="icon"` + `destructive` closely enough that no new
  variant names were needed.
- New primitives: `AnimatedProgressBar`, `UsageStatCard`, `SubjectCard` (optional
  trailing `action` slot kept as a sibling of its `Link`, generalizing the
  delete-button-nesting fix from an earlier increment), `PlanCard`,
  `lib/subjectBadgeTint.ts` (stable per-subject color hash).
- Dashboard/Subjects/Billing rewritten on top of these; Billing now compares all
  three plans (not just upgrade targets), Dashboard's usage section is a condensed
  2-tile grid, `UsageMeters` keeps the fuller detail on Billing only.
- `docs/FRONTEND.md` updated to match the new palette/shell/spacing rules.
- Tests: 10 new files, ~30 new tests. Frontend **178 passed** (45 files, up from
  161/39), `tsc`/`eslint` clean, `npm run build` succeeds (same 14 routes).
- Hit the `rm -rf .next`-while-`next dev`-is-running failure mode a third time this
  project — caught before the build by checking the port first every time, not left
  for the user.
- **Not browser-verified** (standing gap, no browser here): the sidebar's actual
  look, the progress-bar animation, mobile collapse, and card hover feel.

## 2026-07-18 — Frontend redesign Increment 4 (final): Dashboard-as-hub + polish
Closes the redesign roadmap. Frontend-only. Plus the deferred Increment-1 add-ons later
pages needed: skeleton loaders, `EmptyState`, `ErrorState`.
Commit: `feat(frontend): Dashboard-as-hub, interactive subject cards, app-wide polish`.
- New primitives: `ui/skeleton.tsx` (shimmer, `aria-hidden`), `EmptyState`/`ErrorState`
  (icon+title+description+action / icon+message+Retry, both take already-translated
  props rather than calling `useTranslations` themselves, same reasoning as the
  existing `UpgradePrompt`). `Card` gained `interactive`/`selected` props (hover
  elevation + accent ring, purely visual — no keyboard/click handling of its own) —
  backward-compatible, every existing static `<Card>` usage unaffected.
- New pure helpers (all tested): `subjectCardStats` (dashboard card mini-stats from
  `SubjectProgress`), `onboardingChecklist` (3-step "getting started" checklist
  derived from existing `GET /progress` data, no new tracking), `usageSeverity`
  (`normal`/`warning`/`atLimit`, escalating at 80% — before the cap hits, unlike the
  existing reactive 402 path). `components/usage-hint.tsx` renders that severity.
- Dashboard fully rewritten as a hub: personalized greeting (Clerk's
  `useUser().firstName` — confirmed exported/typed against the installed
  `@clerk/nextjs@7.5.18` before relying on it, this project's had a Clerk API surprise
  before), a checklist card (hidden once done), the plan/usage summary, a "New
  subject" quick action, and the subject list as a responsive grid of interactive
  cards with per-subject mini-stats fetched in parallel via `useQueries` (same pattern
  the Ask page's conversation previews already use) — capped at 6 with a "view all N"
  link. Skeleton/EmptyState/ErrorState cover loading/empty/error.
- Subjects list: single-column `<ul>` → responsive grid of interactive cards; a
  proactive usage hint next to the create form; fixed a now-stale code comment
  claiming the backend couldn't cascade-delete (it can, since the cascade-delete fix
  above). Quiz/flashcard generate pages each gained the same proactive usage hint
  (confirmed against `billing.service` that quiz+flashcard generation share ONE daily
  cap before assuming it). Progress page got the same Skeleton/EmptyState/ErrorState
  treatment; `ProgressStats` itself untouched.
- Sign-in/sign-up now land on `/dashboard`, not `/subjects` — the hub redesign is
  pointless if nobody lands on it. Home page's signed-out CTA simplified to a single
  "Get started" → `/sign-in` (was "Go to Subjects", which just bounced through Clerk's
  redirect anyway since `/subjects` is protected).
- i18n: every new string on `dashboard`/`subjects` (already-converted pages) goes
  through `t()` — including subjects' Increment-3-era confirm/toast copy that had been
  left in English at the time; redesigning this exact page was the natural point to
  finish that conversion. Quiz/flashcard/progress pages' new strings stayed plain
  English, matching the rest of each untouched page — full conversion stays the
  separate, already-tracked follow-up. Two dead keys removed (`Home.signIn`,
  `Dashboard.viewAll`); all four locale catalogs verified to parse with identical key
  sets (scripted diff).
- Tests: 27 new (skeleton/empty-state/error-state/card/usage-hint components +
  subjectCardStats/onboardingChecklist/usageSeverity helpers). Frontend **161 passed**
  (39 files, up from 134/31), `tsc`/`eslint` clean, `npm run build` succeeds (same 14
  routes). Caught and fixed mid-session (not left for the user): `rm -rf .next` while
  `next dev` was still running wedged it again (same failure mode as Increments 2/3) —
  this time caught before the build by checking the port first, stopping the process,
  building, then restarting `next dev` and confirming it actually served the homepage.
- **Not browser-verified** (standing gap, no browser here): dashboard rendering,
  hover/interactive card feedback, greeting personalization, sign-in/up redirect.

## 2026-07-18 — Test: lock in the document-upload enqueue-failure behavior
Found live: uploading a document 500s with no CORS header (browser reports it as a
CORS failure) when the local Inngest Dev Server isn't running — `enqueue_document_
processing` raises `SendEventsError` after `create_document` already committed the row
and uploaded to R2, and no app-wide handler catches it. Added a regression test
locking in this "raises loudly" behavior (same reasoning as a missing
`INNGEST_EVENT_KEY`) and confirming the row + R2 object are already real by the time
it happens. No behavior change. Backend **284 passed** (up from 283), `ruff` clean.
Commit: `test(documents): lock in the enqueue-failure behavior on upload` (`881d461`).

## 2026-07-18 — Backend fix: subject cascade delete
Closes the backend gap Frontend Increment 3 found and flagged (not fixed there —
frontend-only scope). `DELETE /subjects/{subject_id}` on a subject with real content
used to hit an unhandled 500 (no FK cascade, no ordered service-layer delete).
Commit: `fix(subjects): cascade-delete a subject's documents, quizzes, flashcards,
and conversations`.
- **Not a DB-level `ON DELETE CASCADE`, by design**: that would delete `Document` rows
  while leaving their R2 objects orphaned forever. `subjects.service.delete_subject`
  instead enumerates each owned child (owner+subject-scoped) and reuses each module's
  own `delete_document`/`delete_quiz`/`delete_flashcard`/`delete_conversation` —
  the functions that already know how to clean up their own child rows and, for
  documents, the R2 object too. Added `ask.service.list_conversations_by_subject`
  (the existing `list_conversations` is deliberately owner-only, for the
  cross-subject sidebar).
- **Two real problems found during Step 0, before writing the actual fix**: (1) all
  four `delete_*` functions commit internally — calling them in a loop as-is would
  break "one transaction, full rollback on failure" (a later failure would leave
  earlier deletes already committed). Fixed with a keyword-only `commit: bool = True`
  on all four (default preserves every existing call site's behavior — confirmed via
  grep only their own router calls them). (2) A top-level cross-module import in
  `subjects/service.py` is a genuine circular import (`documents.service` already
  imports `subjects.service.get_subject`) — reproduced directly
  (`ImportError: cannot import name 'get_subject' from partially initialized module`)
  before fixing it by moving the four imports inside `delete_subject`'s body.
- **One accepted non-atomic edge, documented in the docstring**: `delete_document`'s R2
  delete still happens immediately regardless of `commit` (R2 has no transaction to
  roll back) — an outer-transaction failure after some R2 objects were already removed
  resurrects their `Document` rows via rollback while the R2 objects stay gone. Same
  tradeoff a single document delete already accepts, just visible at a larger scale;
  not made transactional, per the task's explicit instruction.
- Confirmed via `grep 'foreign_key="subjects.id"'`: exactly the four tables named
  (documents, quizzes, flashcards, conversations), plus `document_chunks`/
  `quiz_questions`/`conversation_turns` handled transitively — nothing missed.
- Tests (`test_subjects.py`, offline, R2 mocked): a subject seeded with one of each
  child type is deleted → every child row actually gone (re-queried directly, not just
  the parent lookup returning `None`) and its R2 object gone from the fake store,
  while a second owner's identically-shaped data is completely untouched (the
  cross-tenant assertion). Plus the existing empty-subject test kept, and a new one for
  the enumeration loops being genuine no-ops on an empty subject. Backend
  **283 passed** (11 deselected live, up from 281/10), `ruff check` clean.
- **Live-verified** against real Neon + R2 (`-m live`): a real subject with a real
  ingested document (real `create_document` + `process_document`) deleted via
  `delete_subject`; confirmed the DB rows and the real R2 object are gone. Queried Neon
  and R2 directly by the test's owner id afterward, outside the test itself: 0
  subjects, 0 documents, 0 chunks, 0 R2 objects — confirmed clean, not just asserted.
- Frontend unchanged — Increment 3's "Please try again" delete-error toast is now
  reachable only for genuine failures, not the previously near-guaranteed 500.

## 2026-07-18 — Frontend redesign Increment 3: interaction gaps
Increment 3 of ~4, gated on a `tekshir` review before Increment 4. Frontend-only, no
backend change (a real backend gap was found and flagged, not fixed here — see below).
Commit: `feat(frontend): interaction gaps — confirm, toast, subject delete`.
- Replaced all 4 `window.confirm` sites (delete-document, delete-quiz, delete-flashcard,
  delete-conversation) with the shared `useConfirm()` from Increment 1 — async click
  handlers, early `return` on cancel. Grep-confirmed zero `window.confirm`/`window.alert`
  remain under `src/`.
- Routed delete/generate/create/upload feedback through `toast()`, replacing the inline
  `*Error` state paragraphs FRONTEND.md §3.2 says are the wrong pattern for transient
  failures: document/quiz/flashcard/conversation/subject delete, document upload, quiz
  generate, flashcard generate, subject create. The 402 path is the deliberate exception
  (§3.3) — `parsePlanLimitError(...)` is computed once per failure and only toasts when
  it's `null`, so a 402 shows only the inline `<UpgradePrompt>`, never also a toast.
  `UpgradePrompt` needed no restyling — it already reads through Increment 1's palette.
- Added subject delete: `DELETE /subjects/{subject_id}` already existed on the backend
  and was already typed in `schema.d.ts`, so no schema regeneration. Destructive icon
  button per subject card on `subjects/page.tsx`, confirm-guarded, toasting both
  outcomes. Restructured the subject card so the delete button is a sibling of the
  `Link`, not nested inside it (the whole card used to be one `<Link>` — a delete click
  would have also navigated); mirrors the pattern `quizzes/page.tsx` already used.
- **Backend gap found, not fixed (frontend-only scope)**: none of the `subject_id` FKs
  on `documents`/`quizzes`/`flashcards` carry `ON DELETE CASCADE`, and the only existing
  delete-subject test covers an empty subject only — deleting a subject with real
  content will hit a Postgres FK-violation, likely an unhandled 500. The confirm
  dialog's copy deliberately does NOT claim cascading deletion; `toast.error` still
  degrades gracefully if that 500 happens. Flagged in `docs/PROGRESS.md` "Next" — needs
  a real fix (`ondelete="CASCADE"` via a new migration, or an explicit ordered delete in
  `subjects.service.delete_subject`) before the button is safe on a non-empty subject.
- `subjects/page.tsx`'s new confirm/toast/delete strings stayed English on purpose even
  though that page is already `useTranslations`-converted — matching the other 3
  (still-English) pages this increment touches was the explicit scope; converting these
  specific new strings is left to the tracked i18n follow-up.
- No new pure logic — every change was mutation wiring + JSX inside existing page
  components, nothing to extract to `lib/`. `tsc --noEmit` clean, `eslint` clean,
  **134 passed** (31 files, unchanged), `npm run build` succeeds (same 14 routes/URLs).
- **Not browser-verified** (standing gap, no browser here): confirm-dialog focus-trap/
  Esc, toast rendering/stacking, and the actual subject-delete round-trip (empty and
  non-empty, to observe the backend gap first-hand).

## 2026-07-18 — Frontend redesign Increment 2: shared AppShell + navigation
Increment 2 of ~4, gated on a `tekshir` review before Increment 3. Frontend-only.
Commit: `feat(frontend): shared AppShell + navigation (redesign increment 2)` (`ea7ae20`).
- One `AppShell` (`components/app-shell.tsx`) now owns nav + identity/theme/language
  controls for every authed page — persistent header (Dashboard · Subjects · Plan &
  billing, active-item highlighting via a new pure `lib/navItems.ts` helper) +
  `LanguageSwitcher` + `ThemeToggle` + `UserButton`, plus a `ui/dropdown-menu` mobile
  sheet holding the same three destinations below `sm`.
- **Step 0 verification, before writing code**: read `@base-ui/react@1.6.0`'s actual
  `MenuLinkItem` type declarations + runtime source — confirmed `render={<Link .../>}`
  works, and that it defaults `closeOnClick` to `false` (unlike regular `Menu.Item`,
  which defaults `true`) with no modifier-key guard in either case — so the mobile sheet
  passes `closeOnClick` explicitly rather than relying on the default.
- Adopted via `app/(app)/layout.tsx` wrapping `{children}` in `<AppShell>`. Every authed
  page moved into the `(app)` route group via `git mv` (URLs unchanged — route groups
  are URL-transparent): `dashboard`, `subjects` + all subject-scoped sub-routes, and
  `billing`. Home and sign-in/sign-up stay outside the group.
- Removed the now-duplicated hand-rolled headers (`LanguageSwitcher` + nav button +
  `UserButton` row) from `dashboard`/`subjects`/`billing` — kept just each page's `<h1>`.
- Small fix found in review: `ui/toast.tsx`'s toast transition classes used Base UI's
  non-existent `data-[ending]`/`data-[starting]` attributes instead of the real
  `-style` suffix — fixed, toasts now actually fade.
- Two new i18n keys (`Nav.subjects`, `Nav.menu`) added to `en.json` and mirrored into
  `uz.json`/`ko.json`/`ru.json`.
- Tests: `lib/navItems.test.ts` (7) + `components/app-shell.test.tsx` (3, `next/navigation`
  + `@clerk/nextjs` stubbed). One surprise while writing them: Base UI's `Button`
  rendered as an `<a>` via `render` keeps `role="button"`, not the anchor's native
  `role="link"` — tests query accordingly. `tsc --noEmit` clean, `eslint` clean,
  **134 passed** (31 files, up from 125), `npm run build` succeeds — route list confirms
  every moved page kept its exact URL.
- **Not browser-verified** (standing gap, no browser here): mobile nav sheet
  open/collapse, active-item highlighting, theme toggle, and the language switcher now
  living in the shell.

## 2026-07-18 — Frontend redesign Increment 1: design-system foundation
Phased UI/UX overhaul, increment 1 of ~4 (each gated on a `tekshir` review before the
next). Frontend-only, no backend change. Two commits.
- **Commit A (docs)**: amended `docs/FRONTEND.md` — §2 palette items 7–8 (teal accent, warm
  neutrals, `--warning`, real chart ramp), new §3 (overlays/confirmations/toasts — no
  `window.confirm`, no inline error text), new §4 (shared app shell + nav), renumbered
  General → §5. Added the phased redesign roadmap to `PROGRESS.md` "Next".
- **Commit B (foundation)**:
  - **Palette** (`globals.css`, OKLCH, light + dark): kept indigo `--primary`; replaced the
    gray `--accent` with **teal**; **warmed the neutrals** (a hint of chroma at hue ~80 in
    background/card/muted/secondary/border, never pure gray); added `--warning` /
    `--warning-foreground`; replaced the grayscale `--chart-1..5` with a **real categorical
    ramp** (blue/green/magenta/yellow/aqua) taken from the **dataviz** reference palette.
    **Loaded the `dataviz` skill first**, converted its validated hexes to OKLCH, and
    **contrast-checked every changed text pair against WCAG AA in both themes** (all ≥ 4.5:1;
    the one borderline — light accent-on-white at 4.46 — was darkened to clear 4.85).
  - **Base UI `ui/*` wrappers** (Step 0: introspected the installed `@base-ui/react@1.6.0`
    `.d.ts` for each primitive before wiring — confirmed the parts, the `data-*-style`
    transition attrs, and that the **toast manager** (`createToastManager`/`useToastManager`)
    is runtime-exported from the `toast` namespace): `ui/dialog.tsx`, `ui/alert-dialog.tsx`,
    `ui/toast.tsx` (global `toastManager` + `toast()` helper with `.success/.error/.warning`
    + a `<Toaster/>`, each toast paired with a type icon — never colour alone), and
    `ui/dropdown-menu.tsx` (Base UI `menu`, for the Increment 2 nav collapse).
  - **`useConfirm`** (`components/confirm-provider.tsx`) — a promise-based
    `window.confirm` replacement over `ui/alert-dialog`. The choice is recorded in a ref on
    click and the promise is settled exactly once in `onOpenChange`, so there's no
    button-vs-close ordering race and an Esc/outside dismiss resolves `false`. Pure
    state/label logic extracted to `lib/confirmState.ts` and unit-tested (7 tests).
  - **Dark mode**: added **next-themes** 0.4.6 (`attribute="class"`, `defaultTheme="system"`)
    — verified it works with Tailwind v4's `@custom-variant dark (&:is(.dark *))` (it sets
    `class="dark"` on `<html>`, which the variant keys off; no cookie fallback needed). A
    `ThemeToggle` (lucide sun/moon, mounted-guarded to avoid hydration mismatch);
    `<html suppressHydrationWarning>`. Providers now nest ThemeProvider → QueryClient →
    ToastProvider → ConfirmProvider → children + `<Toaster/>`.
  - **Not yet adopted by pages** — this increment only *adds* the system; wiring
    confirms/toasts/shell into pages is Increments 2–3. Nothing calls `useConfirm`/`toast`
    yet, and no shell exists yet, by design.
  - Tests +7 (`confirmState.test.ts`). Frontend **125 passed** (29 files, up from 118/28),
    `tsc --noEmit` clean, `eslint` clean, `npm run build` succeeds.
  - **Not browser-verified** — no browser with real Clerk auth here, so the theme toggle's
    live class-swap, overlay focus-trap/Esc behaviour, and toast rendering are unverified in
    a real browser (standing gap). Palette contrast, API wiring, types, and build are all
    verified offline.

## 2026-07-18 — next-intl foundation + language switcher + first page slice (Phase 5 groundwork)
- Wired **next-intl 4.13.2** in the **"without i18n routing"** mode
  (https://next-intl.dev/docs/getting-started/app-router/without-i18n-routing): the active
  locale lives in a `locale` **cookie**, not the URL — so there's **no `[locale]` segment,
  no route restructuring, and no next-intl middleware**. `clerkMiddleware` in
  `src/middleware.ts` stays the only middleware, untouched.
- **Step 0 introspection against the installed package** (not memory): confirmed
  `getRequestConfig` returns `{ locale, messages }`; `NextIntlClientProvider` **auto-inherits
  locale+messages** when rendered from a Server Component (v4 — no explicit props needed in
  the layout, explicit only in tests); and the no-middleware claim holds for v4's
  without-routing mode.
- Files: `next.config.ts` wrapped with `createNextIntlPlugin("./src/i18n/request.ts")`;
  `src/i18n/request.ts` (reads the cookie via the async Next 15 `cookies()`, falls back to
  `en`, dynamic-imports the catalog); `src/i18n/locales.ts` (locale list + `resolveLocale`
  hardening — an unknown/edited cookie can't point the import at a missing catalog);
  `src/i18n/setLocale.ts` (server action writing the cookie); root `layout.tsx` now
  **async**, `<html lang={await getLocale()}>`, wraps children in `NextIntlClientProvider`.
- **Locales: en (default), uz, ko, ru.** `messages/en.json` is the source of truth;
  `uz/ko/ru.json` mirror its keys. **⚠️ uz/ko/ru are machine/LLM-drafted starting points
  and NOT production-quality — they need native-speaker review** (flagged in
  `messages/README.md` and PROGRESS "Next"). The Russian `few`/`many` plural forms and
  `по` + dative phrasing in `Dashboard.acrossSubjects` are the most likely to need fixing.
- **LanguageSwitcher** (`src/components/language-switcher.tsx`): native `<select>` (no
  shadcn Select primitive in this repo), semantic tokens, ≥44px target, Languages icon +
  `aria-label` (not identifiable by position alone). On change → `setLocale` server action
  → `router.refresh()`. Placed next to `UserButton` in the dashboard and subjects headers.
- **First page slice converted** to `useTranslations`: **home, subjects list, dashboard**
  (incl. an ICU `plural` for "Across N subjects"). **sign-in/sign-up render Clerk's own
  `<SignIn>`/`<SignUp>` widgets — they carry no app strings of ours, so there was nothing to
  translate there; Clerk's own UI localization (`@clerk/localizations`) is a separate
  follow-up.** All other pages (subject detail, quizzes, flashcards, ask, progress, billing)
  stay English for now — tracked in PROGRESS "Next".
- **Test-harness impact handled**: added `src/lib/test/renderWithIntl.tsx` (wraps in
  `NextIntlClientProvider` with the real `en` catalog) for any translated component under
  test. Only pages (untested here by the codebase's pattern) and the new LanguageSwitcher
  were touched, so no existing component test needed the wrapper.
- Tests (+11, all offline): `locales.test.ts` (5 — `resolveLocale`/`isLocale` reject
  unknown → `en`, incl. a `../../etc/passwd`-style value), `language-switcher.test.tsx`
  (3 — renders one option per locale, reflects the active locale, calls `setLocale` on
  change; `next/navigation` + the server action mocked), `messages.test.ts` (3 — **key
  parity across all four catalogs**, and every locale's `acrossSubjects` ICU plural formats
  without throwing for counts 0/1/2/5/11/21/100 — the one failure mode build/en-only tests
  miss). Frontend **118 passed** (28 files, up from 107/25), `tsc --noEmit` clean, `eslint`
  clean, `npm run build` succeeds (`/` and the converted pages are now `ƒ` dynamic —
  expected, they read the locale cookie).
- **Env side-check** (unrelated to i18n): `frontend/.env` has no `NEXT_PUBLIC_API_URL`, but
  `lib/api/client.ts` falls back to `http://localhost:8000`, so build/dev resolve fine —
  no action needed unless the backend moves off that origin.
- **Not browser-verified** — no browser in this environment, so the language-switch
  cookie→refresh→re-render round-trip is unverified in a real browser (standing gap). The
  cookie read/validation, catalog parity, plural formatting, provider wiring, and build are
  all verified offline.

## 2026-07-18 — 402 upgrade prompt extended to documents/quiz/flashcards (Phase 4)
- Closes the gap the billing-frontend increment below flagged as "a one-liner later":
  the 402 → `<UpgradePrompt>` UX was wired into subject-create only; now every
  plan-limit-guarded create path (subjects, document upload, quiz generation,
  flashcard generation) shows a real upgrade prompt instead of a generic error.
- **Verified reachability before wiring anything** (Step 0): grepped `ensure_can_` across
  `app/modules` — `documents/service.py` calls `ensure_can_upload_document`,
  `quiz/service.py` and `flashcards/service.py` both call `ensure_can_generate` — so a
  402 is genuinely reachable on all three, not assumed.
- **No backend change, no new components/helpers** — reused `UpgradePrompt` and
  `parsePlanLimitError` exactly as shipped. Same shape in all three pages
  (`app/subjects/[subjectId]/page.tsx`, `.../quizzes/page.tsx`, `.../flashcards/page.tsx`),
  mirroring `subjects/page.tsx`: a `limitError` state cleared in `onMutate`, the
  mutation's error branch calls `setLimitError(parsePlanLimitError(response.status,
  error))` before still throwing the existing `new Error(friendly*Error(response.status))`
  — the 402 branch is additive, the existing 415/413/422/502/generic handling in
  `friendlyUploadError`/`friendlyQuizError`/`friendlyFlashcardError` is untouched — and
  the JSX shows `<UpgradePrompt message={limitError.detail}/>` ahead of the existing
  generic error line whenever a 402 was parsed.
- **Considered and rejected a shared hook** for the repeated
  state+`onMutate`+JSX shape: ~4 lines duplicated across 3 pages, and the reference
  pattern (`subjects/page.tsx`) doesn't use one either — introducing an abstraction only
  3 of 4 call sites would share failed the task's own YAGNI bar.
- **No new tests** — this codebase's established pattern is helpers/components tested,
  pages `tsc`/`eslint`/live-browser-verified (no page here has its own test file); the
  logic being wired in already has full coverage from the increment below. Frontend:
  **107 passed** (unchanged), `tsc --noEmit` clean, `eslint` clean, `npm run build`
  succeeds.
- **Not browser-verified** (standing no-browser gap) — the three new prompts want a
  manual trip past each plan cap with real Clerk auth.

## 2026-07-18 — Billing frontend: usage meters + upgrade prompts (Phase 4)
- Consumes the two billing endpoints that already existed (`GET /billing/plan`,
  `POST /billing/checkout`) — **no backend change this increment**. Regenerated
  `frontend/src/lib/api/schema.d.ts` (offline, from `app.openapi()` → `openapi-typescript`,
  identical to the live-server `generate-api-types` script) so the billing routes/schemas
  (`PlanRead`, `PlanLimitsRead`, `PlanUsageRead`, `CheckoutCreateRequest/Response`, `Plan`)
  are typed — no hand-edits.
- **New `/billing` page** (protected — added `/billing(.*)` to `middleware.ts`): current
  plan, usage meters, and upgrade options. Upgrade offers only plans *above* the current
  tier (Free → Pro+Business, Pro → Business, Business → none). The upgrade button calls
  `POST /billing/checkout` with `{plan, success_url}` and redirects the browser to Polar's
  hosted `checkout_url`. `success_url` is `${origin}/billing?upgraded=1`; on return the page
  shows a "payment went through, plan activating" note and refetches the plan (the webhook
  lands the change asynchronously, so it may lag by a moment). Read the `upgraded` flag via
  `window.location.search` in an effect rather than `useSearchParams`, to avoid forcing a
  Suspense boundary.
- **Upgrade prompt on the 402 path**: the subject-create mutation now inspects the response
  and, on a 402, renders `<UpgradePrompt>` (the backend's own message, which already names
  the limit + cap) with an Upgrade → `/billing` button, instead of the generic failure line.
  Wired only into subject-create for now (the visible Free cap); the reusable
  `UpgradePrompt` + `parsePlanLimitError` helper make adding it to document-upload /
  quiz / flashcard generation a one-liner later.
- **Pure helpers, unit-tested** (this codebase's helpers-tested / pages-untested pattern):
  `lib/planLimits.ts` (`meterPercent` — rounded/clamped 0–100, 0 for unlimited/zero cap
  never NaN; `usageMeters` — subjects + daily-generations meters, `atLimit` at the exact
  cap, unlimited handling) and `lib/planLimitError.ts` (`parsePlanLimitError` — validates
  the untyped 402 body shape, null for non-402/malformed, generic-message fallback).
  `max_documents_per_subject` is deliberately not metered — it's a per-subject cap with no
  account-wide number, so it's stated as a rule on the page instead.
- **Components**: `UsageMeters` (bars as `role="img"` with the "used of cap" text in the
  aria-label — never colour alone, per FRONTEND.md; `destructive` fill + text at the cap,
  no bar for unlimited) and `UpgradePrompt`. Dashboard header gained a "Plan & billing"
  link. All semantic tokens, mobile-first.
- Tests: `planLimits.test.ts`, `planLimitError.test.ts`, `usage-meters.test.tsx`,
  `upgrade-prompt.test.tsx`. Frontend **107 passed** (25 files, up from 90/21 — corrected
  from this entry's original 106; the follow-up meter-track fix's test brought it to 107),
  `tsc --noEmit` clean, `eslint` clean, `npm run build` succeeds (`/billing` compiles as a
  static route).
- **Not browser-verified with real Clerk auth** — the standing no-browser gap in this
  environment (noted on every frontend page here). The checkout→Polar redirect and the
  ?upgraded refetch specifically want a manual click-through once a browser is available.

## 2026-07-17 — Polar payment wiring: checkout + webhook (Phase 4 billing, SANDBOX)
- The last blocked Phase 4 item, unblocked by the user's sandbox keys. Polar's only job
  is upserting one `UserPlan` row (DECISIONS.md #7); the entitlement layer was **not**
  redesigned and needed no changes. Still no plan-change endpoint.
- **Step 0 (introspect before writing) earned its keep — it caught a mismatch that would
  have shipped a green, fully-tested, silently dead integration.** All three sandbox
  products (FREE $0 / PRO $20 / Business $100) were **one-time purchases**
  (`recurring_interval: None`), not subscriptions. One-time products never emit
  `subscription.*` events (they emit `order.paid`), so the specced webhook would have
  received *nothing*: checkout would work, tests would pass, and no plan would ever change
  in production. Nothing would ever cancel or expire either — $100 would buy permanently
  unlimited Business. This was escalated rather than guessed (the task's own "a wrong
  number here either cheats a paying user or gives away the product" rule); the user chose
  recurring monthly, and two new monthly products were created via the API (Pro
  `5d19dae1…` $20/mo, Business `653e839c…` $100/mo) preserving the original price points.
  The old one-time products were left untouched for the user to remove.
- **The LIMITS comparison the task asked for: no conflict.** The products carry no caps
  anywhere — empty descriptions, no metadata, no benefits — so nothing in the dashboard
  contradicts `LIMITS`, which stays the only thing enforcing anything. Worth stating
  plainly: nothing corroborates those numbers either, so they still want confirming.
- **Everything was introspected against the installed SDK, not recalled.** That's what
  surfaced the one-time/recurring split (the SDK types `ProductCreateRecurring` and
  `ProductCreateOneTime` separately), the real `validate_event(body, headers, secret)`
  signature, `external_customer_id` as the linkage field, and the `canceled`/`revoked`
  distinction below.
- **`feat(billing)` — client + config** (`app/core/polar_client.py`): one shared client,
  `sandbox`/`production` via `POLAR_SERVER`, **defaulting to sandbox** so a misconfigured
  deploy can't charge a real card. Missing creds → `PolarConfigError` at point of use
  naming the exact env var (same pattern as r2/inngest/embedding). Secrets never logged,
  returned, or embedded in an exception message — asserted by a test, not just intended.
  Kept Polar-only so `app/core` still never imports `app/modules`. Product→plan mapping is
  by **id, not name**: ids are stable, names are mutable labels — and this org's products
  were *already* named inconsistently ("FREE"/"PRO"/"Business"), which is precisely how
  name-matching breaks; mapping by name would also add an API call per webhook. No Free
  product id: Free is the absence of a paid plan, so it is never sold.
- **`feat(billing)` — checkout + webhook**. **Owner linkage is the whole design.** The
  webhook has no Clerk JWT, so `create_checkout` plants the Clerk owner_id as
  `external_customer_id` at the one moment the caller is authenticated; the webhook reads
  it back from `subscription.customer.external_id`, only ever out of a signature-verified
  payload, never from a client-controllable field. Tested that an `owner_id` in the
  request body is ignored in favour of the token's.
- **Signature verification precedes any parsing or DB access**, on the raw
  `await request.body()` (re-serializing parsed JSON changes the bytes and breaks it). The
  SDK delegates to Standard Webhooks: constant-time compare plus a timestamp freshness
  window, so replay protection is free and no crypto is hand-rolled. Bad signature → 403,
  nothing written. **A missing secret raises (500) rather than falling back to "accept"** —
  an unverified webhook is a free-Business-plan bypass.
- **`revoked` downgrades; `canceled` deliberately does not** — the subtlest call here, and
  the task brief's "cancellation must downgrade" would have been wrong. The SDK's own
  docstrings settle it: `canceled` = "cancellation scheduled, customers **might still have
  access until the end of the current period**"; `revoked` = "loses access immediately".
  Downgrading on `canceled` would cut off someone who already paid through period end.
  `past_due` also waits (payment may recover; `revoked` fires if it doesn't).
  `subscription.updated` **is** handled — a mid-period Pro→Business switch fires no
  `active` event, so without it an upgrade would be silently ignored.
- **Downgrade sets `Plan.FREE` instead of deleting the row** — the deliberate choice the
  task asked to document. "No row" does also mean Free, but deleting discards `updated_at`,
  which is the ordering guard: a stale `active` redelivered afterwards would find no row,
  look fresh, and silently re-grant a paid plan for free. One tiny row per ex-subscriber is
  the cheaper trade. Relatedly, **`updated_at` stores the *event's* timestamp, not
  wall-clock**: with processing time, a genuinely newer event that merely arrived a moment
  later would compare as older than the row and be dropped. `_as_utc` normalizes both sides
  — Polar's timestamps are aware, but `updated_at` round-trips through a `TIMESTAMP WITHOUT
  TIME ZONE` column and comes back **naive**, which would `TypeError` on comparison (found
  by reasoning it through, then pinned by the out-of-order tests).
- Unknown product / missing `external_id` / unhandled event type → **200 `ignored`**,
  logged, nothing written. Not errors: a non-2xx would make Polar retry forever an event
  that can never succeed. Not swallowed either — each is logged with why, and the response
  says which outcome happened. Checkout failures surface as real statuses (400/500/502),
  never a 200 with no URL.
- **`test(billing)`** — `test_polar.py`, 37 tests, network-free by default (the client is
  mocked, as with r2/llm). **Signatures are deliberately not mocked**: payloads are signed
  with real HMAC via the same Standard Webhooks library the verifier uses and posted as
  real bytes at the real endpoint — the signature check is the only thing between the
  public internet and a free Business plan, so stubbing it would prove nothing. Includes a
  body **tampered after signing** (403), both out-of-order directions, canceled/past_due
  not downgrading, and tenant isolation. Backend **281 passed** (10 deselected live, up
  from 244/9), ruff clean; **the 244 pre-existing tests needed no changes**.
- **Live-verified in two halves, and the second is honestly only partial:**
  1. **Checkout — genuinely live.** Real sandbox checkout via the real API with a throwaway
     owner id, read back from Polar to confirm `external_customer_id` persisted. Learned
     empirically that `checkouts.list(external_customer_id=…)` can't find an *unpaid*
     checkout (the filter resolves through the customer relation; `customer_id` is `None`
     until payment), so the test matches on the returned URL — whose last segment, also
     learned the hard way, is a client secret rather than the checkout id.
  2. **Webhook — Polar has never actually delivered an event to it.** No Polar CLI here, so
     no `polar listen` tunnel. What *was* done: the real app under uvicorn on a real socket
     against real Neon, driven with payloads signed by the **real** `POLAR_WEBHOOK_SECRET`
     from `.env` — valid → 200 `applied` + `pro` in Neon; bad signature → **403, plan
     unchanged**; duplicate → `ignored_stale`; canceled → `ignored`, still `pro`; updated →
     `business`; stale → `ignored_stale`; revoked → `free`. Throwaway owner; Neon at 0
     `UserPlan` rows before and after. That proves transport + signature + DB write. It does
     **not** prove Polar's real delivery format, nor that the configured secret matches how
     events will actually be delivered (`polar listen` prints its own, which may differ from
     the dashboard's). Called out in PROGRESS Blockers rather than glossed as "verified".
- Commits: `feat(billing): add Polar client + config`, `feat(billing): Polar checkout +
  webhook -> UserPlan`, `test(billing): Polar checkout, webhook signatures, ordering,
  tenant isolation`, `docs: record Polar payment wiring increment`.

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
