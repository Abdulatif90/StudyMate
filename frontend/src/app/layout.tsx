import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import { resolveClerkLocalization } from "@/i18n/clerkLocalization";
import { resolveLocale } from "@/i18n/locales";
import { Providers } from "./providers";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "StudyMate",
  description: "AI study assistant — cited Q&A over your own materials.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Active locale comes from the "locale" cookie via i18n/request.ts (no [locale] URL
  // segment — "without i18n routing" mode). Drives <html lang> for a11y/SEO.
  const locale = await getLocale();
  // next-intl types getLocale()'s return as plain `string` (no augmentation in this repo),
  // so re-narrow through resolveLocale — also the app-wide convention for trusting a
  // locale value (see i18n/request.ts, i18n/setLocale.ts).
  const clerkLocalization = resolveClerkLocalization(resolveLocale(locale));

  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      localization={clerkLocalization}
    >
      {/* suppressHydrationWarning: next-themes sets class="dark" on <html> via a
          pre-hydration script, so the server/client class attributes intentionally differ. */}
      <html lang={locale} suppressHydrationWarning>
        <body className={`${geistMono.variable} antialiased`}>
          {/* Rendered from a Server Component, so NextIntlClientProvider auto-inherits
              the locale + messages resolved in i18n/request.ts — no explicit props. */}
          <NextIntlClientProvider>
            <Providers>{children}</Providers>
          </NextIntlClientProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
