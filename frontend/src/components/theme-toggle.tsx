"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/**
 * Light/dark toggle. Renders a stable placeholder icon until mounted — `resolvedTheme` is
 * only known on the client, so gating the icon on `mounted` avoids a hydration mismatch.
 * next-themes persists the choice (localStorage) across reloads.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="outline"
      size="icon"
      aria-label={
        !mounted ? "Toggle theme" : isDark ? "Switch to light mode" : "Switch to dark mode"
      }
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {mounted && isDark ? <Moon className="size-4" /> : <Sun className="size-4" />}
    </Button>
  );
}
