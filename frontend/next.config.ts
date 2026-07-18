import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl "without i18n routing" mode: the active locale lives in a cookie (read in
// src/i18n/request.ts), NOT in the URL — so there is no [locale] segment and no next-intl
// middleware. clerkMiddleware in src/middleware.ts stays the only middleware.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {};

// withSentryConfig wraps the build to upload source maps IF a SENTRY_AUTH_TOKEN (+
// org/project) is configured — none of that exists in this environment yet, so
// `silent`/`disableLogger` just keep an unconfigured build quiet instead of printing
// "skipping sourcemap upload" noise on every `next build`. Actual error capture
// (instrumentation.ts / instrumentation-client.ts) doesn't depend on any of this.
export default withSentryConfig(withNextIntl(nextConfig), {
  silent: true,
  webpack: { treeshake: { removeDebugLogging: true } },
});
