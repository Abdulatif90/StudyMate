/** Supported UI locales. `en` is the source-of-truth catalog; `uz`/`ko`/`ru` are
 * machine/LLM-drafted starting points that still need native review (see the header
 * note in each messages/*.json and docs/PROGRESS.md). */
export const LOCALES = ["en", "uz", "ko", "ru"] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

/** Endonyms (each language's name in its own script) — the accessible convention for a
 * language switcher, so a speaker recognises their own language regardless of the UI's
 * current locale. */
export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  uz: "O‘zbekcha",
  ko: "한국어",
  ru: "Русский",
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/**
 * Resolve an untrusted locale value (e.g. a cookie the user could hand-edit) to a
 * supported locale, falling back to `en`. Anything unknown, missing, or malformed
 * becomes the default rather than being trusted into a failed `import()` of a missing
 * catalog.
 */
export function resolveLocale(value: string | undefined | null): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
