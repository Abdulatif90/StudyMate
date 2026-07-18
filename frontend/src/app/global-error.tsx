"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

/**
 * Next.js App Router's top-level error boundary — catches rendering errors that
 * escape every page/layout's own boundary. `Sentry.captureException` is itself a
 * no-op if Sentry was never initialized (no NEXT_PUBLIC_SENTRY_DSN), so this file
 * needs no env check of its own. Falls back to Next's own default error page (same
 * one Next renders here when no `global-error.tsx` exists at all) rather than a
 * custom design — this boundary should be rare and unstyled is fine.
 */
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body>
        <NextError statusCode={0} />
      </body>
    </html>
  );
}
