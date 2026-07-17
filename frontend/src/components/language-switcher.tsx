"use client";

import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { LOCALES, LOCALE_LABELS } from "@/i18n/locales";
import { setLocale } from "@/i18n/setLocale";

/**
 * Language switcher for the app shell. A native `<select>` (no shadcn Select primitive in
 * this repo) styled with semantic tokens — accessible by default, ≥44px touch target,
 * paired with a Languages icon so the control isn't identifiable by position alone.
 *
 * On change it calls the `setLocale` server action (writes the "locale" cookie) then
 * `router.refresh()`, so the next server render reads the new cookie and streams messages
 * for the chosen locale. The `<select>` is disabled during the transition.
 */
export function LanguageSwitcher() {
  const activeLocale = useLocale();
  const t = useTranslations("Language");
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <label className="relative inline-flex items-center">
      <Languages
        aria-hidden
        className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
      />
      <span className="sr-only">{t("label")}</span>
      <select
        aria-label={t("label")}
        value={activeLocale}
        disabled={isPending}
        onChange={(event) => {
          const next = event.target.value;
          startTransition(async () => {
            await setLocale(next);
            router.refresh();
          });
        }}
        className="h-10 rounded-lg border border-border bg-background pl-8 pr-2 text-sm text-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
      >
        {LOCALES.map((locale) => (
          <option key={locale} value={locale}>
            {LOCALE_LABELS[locale]}
          </option>
        ))}
      </select>
    </label>
  );
}
