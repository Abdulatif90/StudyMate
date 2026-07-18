import { enUS, koKR, ruRU } from "@clerk/localizations";
import type { LocalizationResource } from "@clerk/shared/types";
import type { Locale } from "./locales";

/**
 * Maps each app locale to Clerk's own localization resource, so the `<SignIn>`/`<SignUp>`
 * widget UI (labels, errors, button text — Clerk's own strings, not ours) follows the
 * app's active next-intl locale instead of always rendering in English.
 *
 * `@clerk/localizations` (checked in v4.13.5) ships `enUS`, `koKR`, `ruRU` among its 50
 * exports, but no Uzbek variant — there is no `uzUZ`/`uzUz` to import. Hand-writing a
 * partial translation of Clerk's internal keys would be fragile and out of scope, so `uz`
 * intentionally falls back to `enUS`: Clerk's widget stays English for Uzbek users while
 * the rest of the app renders in Uzbek. Revisit if Clerk adds Uzbek support upstream.
 */
const LOCALE_TO_CLERK: Record<Locale, LocalizationResource> = {
  en: enUS,
  uz: enUS,
  ko: koKR,
  ru: ruRU,
};

/** Resolve the Clerk localization resource for the app's active locale. */
export function resolveClerkLocalization(locale: Locale): LocalizationResource {
  return LOCALE_TO_CLERK[locale];
}
