// Client-side Sentry init — the modern replacement for `sentry.client.config.ts`
// (deprecated by @sentry/nextjs in favor of this file; see its own webpack config for
// the exact deprecation check). Env-gated: a missing DSN means Sentry is simply off in
// the browser, never a crash — same convention as every optional key in this project
// (see backend/app/core/sentry.py).
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    // PII scrub: `sendDefaultPii` defaults to false (no IP/cookies attached
    // automatically) — kept explicit here so this stays true even if a future SDK
    // bump ever flips that default. The only user identifier attached to error
    // context is the Clerk user id, set explicitly via `Sentry.setUser({ id })` in
    // `app/providers.tsx` — never email or name.
    sendDefaultPii: false,
  });
}

// Required by the SDK to instrument App Router navigations (it warns at build time
// otherwise). A safe no-op export when `dsn` is unset — Sentry.init was never called.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
