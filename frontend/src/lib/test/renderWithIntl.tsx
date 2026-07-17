import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";
import { DEFAULT_LOCALE, type Locale } from "@/i18n/locales";
import enMessages from "../../../messages/en.json";

/**
 * Render a component that calls `useTranslations()`/`useLocale()` under a
 * NextIntlClientProvider wired with the real `en` catalog. Any translated component
 * would otherwise throw ("No intl context found") in a bare `render`. Defaults to the
 * `en` locale; pass `{ locale }` to exercise another.
 */
export function renderWithIntl(
  ui: ReactElement,
  { locale = DEFAULT_LOCALE, ...options }: { locale?: Locale } & Omit<RenderOptions, "wrapper"> = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={enMessages}>
        {children}
      </NextIntlClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
