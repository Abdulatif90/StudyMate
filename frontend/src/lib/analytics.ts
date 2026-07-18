import posthog from "posthog-js";

/**
 * The full, deliberate set of product events this app captures — PostHog's
 * autocapture is off (see `providers.tsx`), so nothing is tracked outside this list.
 * Keys are the call-site name; values are the event name PostHog actually sees.
 */
const EVENTS = {
  subjectCreated: "subject_created",
  documentUploaded: "document_uploaded",
  quizGenerated: "quiz_generated",
  flashcardsGenerated: "flashcards_generated",
  questionAsked: "question_asked",
  checkoutStarted: "checkout_started",
} as const;

export type AnalyticsEvent = keyof typeof EVENTS;

/**
 * Fires a named product event. A no-op when analytics isn't configured (no
 * `NEXT_PUBLIC_POSTHOG_KEY`) or outside the browser (SSR) — same env-gated convention
 * as Sentry (see `backend/app/core/sentry.py`, `instrumentation-client.ts`). Gated here
 * directly (not just by `PostHogProvider` never mounting) so this function is safe to
 * call unconditionally from any mutation's `onSuccess`, regardless of whether the
 * provider happens to be in the tree.
 */
export function captureEvent(event: AnalyticsEvent, properties?: Record<string, unknown>): void {
  if (typeof window === "undefined") return;
  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;
  posthog.capture(EVENTS[event], properties);
}
