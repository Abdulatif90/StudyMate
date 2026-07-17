"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * Wraps next-themes. Uses `attribute="class"`, which sets `class="dark"` on `<html>` —
 * exactly what Tailwind v4's `@custom-variant dark (&:is(.dark *))` in globals.css keys
 * off, so no extra config is needed. `<html>` carries `suppressHydrationWarning` (see
 * app/layout.tsx) because the class is applied by next-themes' pre-hydration script.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
