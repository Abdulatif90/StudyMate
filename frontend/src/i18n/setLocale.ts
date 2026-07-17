"use server";

import { cookies } from "next/headers";
import { isLocale } from "./locales";

/**
 * Server action: persist the chosen UI locale in the "locale" cookie. The
 * LanguageSwitcher calls this and then `router.refresh()`, so the next RSC render reads
 * the new cookie in `i18n/request.ts` and streams messages for the new locale.
 *
 * An unsupported value is ignored (no cookie written) rather than trusted — the cookie
 * feeds a dynamic catalog import, so only known locales may reach it. Not httpOnly: it's
 * a UI preference, not a secret, and nothing security-sensitive keys off it.
 */
export async function setLocale(locale: string): Promise<void> {
  if (!isLocale(locale)) return;
  const cookieStore = await cookies();
  cookieStore.set("locale", locale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365, // one year
    sameSite: "lax",
  });
}
