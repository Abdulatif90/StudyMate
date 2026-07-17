import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

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

  return (
    <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up">
      {/* suppressHydrationWarning: next-themes sets class="dark" on <html> via a
          pre-hydration script, so the server/client class attributes intentionally differ. */}
      <html lang={locale} suppressHydrationWarning>
        <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
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
