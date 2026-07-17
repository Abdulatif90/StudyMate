import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";
import { resolveLocale } from "./locales";

/**
 * Per-request i18n config (next-intl "without i18n routing"). There's no `[locale]`
 * URL segment, so `requestLocale` is always undefined here — the active locale comes
 * from the "locale" cookie instead, set by the LanguageSwitcher. An unknown/edited
 * cookie value falls back to `en` via `resolveLocale`, so the dynamic `import()` below
 * can never be pointed at a missing catalog.
 *
 * Next 15's `cookies()` is async — hence the `await`.
 */
export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get("locale")?.value);

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
