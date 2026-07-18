"use client";

import { useUser } from "@clerk/nextjs";
import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";
import { useEffect } from "react";

/**
 * Attaches the signed-in Clerk user id — and ONLY the id, never email/name — to both
 * Sentry error context and PostHog's identified-user id, so errors/events can be traced
 * back to an account without carrying PII. Each call is itself a no-op unless that
 * tool's own env key is set (Sentry/PostHog init already gate on their DSN/key; this
 * additionally checks so `posthog.identify`/`Sentry.setUser` are never called against
 * an uninitialized client). Renders nothing — this is a side-effect-only component,
 * mounted once near the root (`app/providers.tsx`).
 */
export function ObservabilityIdentity() {
  const { user, isLoaded } = useUser();

  useEffect(() => {
    if (!isLoaded) return;

    const userId = user?.id ?? null;

    if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
      Sentry.setUser(userId ? { id: userId } : null);
    }

    if (process.env.NEXT_PUBLIC_POSTHOG_KEY) {
      if (userId) {
        posthog.identify(userId);
      } else {
        posthog.reset();
      }
    }
  }, [isLoaded, user]);

  return null;
}
