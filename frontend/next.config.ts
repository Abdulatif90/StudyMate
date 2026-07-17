import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl "without i18n routing" mode: the active locale lives in a cookie (read in
// src/i18n/request.ts), NOT in the URL — so there is no [locale] segment and no next-intl
// middleware. clerkMiddleware in src/middleware.ts stays the only middleware.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {};

export default withNextIntl(nextConfig);
