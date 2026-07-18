"use client";

import { UserButton } from "@clerk/nextjs";
import { Menu as MenuIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLinkItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { isNavItemActive, NAV_ITEMS } from "@/lib/navItems";

/**
 * Persistent app shell for every authed page (FRONTEND.md §4) — nav + theme toggle +
 * language switcher + UserButton, so no page hand-rolls its own header. Below `sm` the
 * primary nav collapses into a `ui/dropdown-menu` sheet rather than disappearing, so
 * every destination (billing included) stays reachable on every screen.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("Nav");

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-background">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-2 px-4 sm:px-6 lg:px-8">
          <Link href="/dashboard" className="shrink-0 text-base font-semibold">
            StudyMate
          </Link>

          <nav aria-label={t("menu")} className="hidden items-center gap-1 sm:flex">
            {NAV_ITEMS.map((item) => {
              const active = isNavItemActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <Button
                  key={item.href}
                  variant={active ? "secondary" : "ghost"}
                  nativeButton={false}
                  aria-current={active ? "page" : undefined}
                  render={
                    <Link href={item.href}>
                      <Icon className="size-4" aria-hidden />
                      {t(item.translationKey)}
                    </Link>
                  }
                />
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
            <UserButton />

            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline" size="icon" className="sm:hidden" aria-label={t("menu")}>
                    <MenuIcon className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent className="sm:hidden">
                {NAV_ITEMS.map((item) => {
                  const active = isNavItemActive(pathname, item.href);
                  const Icon = item.icon;
                  return (
                    <DropdownMenuLinkItem
                      key={item.href}
                      aria-current={active ? "page" : undefined}
                      className={active ? "bg-muted font-medium" : undefined}
                      // A plain tap should close the sheet after navigating; ctrl/cmd/
                      // middle-click (open in a new tab, current tab doesn't navigate)
                      // will also close it — an accepted tradeoff for a mobile nav sheet,
                      // not a broken one (Base UI's LinkItem itself has no modifier-key
                      // guard around closeOnClick, confirmed by reading its source).
                      closeOnClick
                      render={
                        <Link href={item.href}>
                          <Icon className="size-4" aria-hidden />
                          {t(item.translationKey)}
                        </Link>
                      }
                    />
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>
    </div>
  );
}
