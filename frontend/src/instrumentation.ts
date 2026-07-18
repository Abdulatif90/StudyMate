// Server + edge Sentry init, via Next.js's `instrumentation.ts` convention (the
// `register()` hook Next calls once per runtime at process startup) — the modern
// replacement for `sentry.server.config.ts`/`sentry.edge.config.ts`. Same env gate as
// `instrumentation-client.ts`: no NEXT_PUBLIC_SENTRY_DSN, no init, never a crash.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  // `NEXT_RUNTIME` distinguishes the Node.js server runtime from the Edge runtime —
  // both call `register()`, so this file (not two separate ones) covers both.
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init({ dsn, sendDefaultPii: false });
  }
}

// Captures errors thrown while rendering React Server Components (a class of error
// instrumentation-client.ts's browser-only init can't see) — a no-op if `register()`
// above never called `Sentry.init` (captureException-before-init is a safe no-op in
// every Sentry JS SDK).
export const onRequestError = Sentry.captureRequestError;
