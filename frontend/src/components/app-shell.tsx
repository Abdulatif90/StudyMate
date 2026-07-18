"use client";

import { UserButton, useUser } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Menu as MenuIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AnimatedProgressBar } from "@/components/ui/animated-progress-bar";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLinkItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useApiClient } from "@/lib/api/useApiClient";
import { isNavItemActive, NAV_ITEMS } from "@/lib/navItems";
import { PLAN_LABELS, usageMeters } from "@/lib/planLimits";
import { cn } from "@/lib/utils";

const SIDEBAR_WIDTH_CLASS = "lg:w-[236px]";

function BrandMark() {
  return (
    <Link href="/dashboard" className="flex shrink-0 items-center gap-2 px-6 py-6">
      <span className="flex size-8 items-center justify-center rounded-lg bg-gradient-brand text-white">
        <BookOpen className="size-4" aria-hidden />
      </span>
      <span className="font-brand text-lg font-semibold text-white">StudyMate</span>
    </Link>
  );
}

function SidebarNav({ pathname, t }: { pathname: string; t: ReturnType<typeof useTranslations> }) {
  return (
    <nav aria-label={t("menu")} className="flex flex-col gap-1 px-3">
      {NAV_ITEMS.map((item) => {
        const active = isNavItemActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150",
              active
                ? "bg-gradient-brand text-white"
                : "text-white/70 hover:bg-sidebar-accent hover:text-white",
            )}
          >
            <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
            {t(item.translationKey)}
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarUsageWidget() {
  const api = useApiClient();
  const t = useTranslations("Dashboard");
  const tUsage = useTranslations("Usage");
  const planQuery = useQuery({
    queryKey: ["billing", "plan"],
    queryFn: async () => {
      const { data, error } = await api.GET("/billing/plan");
      if (error) throw error;
      return data;
    },
  });
  if (!planQuery.data) return null;

  const meters = usageMeters(planQuery.data);

  return (
    <div className="mx-3 mt-4 flex flex-col gap-3 rounded-lg bg-sidebar-accent/60 p-3">
      {meters.map((meter) => (
        <div key={meter.key} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="text-white/70">{tUsage(meter.key)}</span>
            <span className="font-medium text-white">
              {meter.unlimited ? "∞" : `${meter.used}/${meter.cap}`}
            </span>
          </div>
          {!meter.unlimited && (
            <AnimatedProgressBar
              percent={meter.percent}
              trackClassName="h-1 bg-white/15"
              fillClassName={meter.atLimit ? "bg-warning-fill" : "bg-gradient-brand"}
            />
          )}
        </div>
      ))}
      <Link href="/billing" className="text-xs font-medium text-sidebar-ring hover:underline">
        {t("managePlanLink")}
      </Link>
    </div>
  );
}

function SidebarProfile() {
  const { user } = useUser();
  const t = useTranslations("Nav");
  const api = useApiClient();
  const planQuery = useQuery({
    queryKey: ["billing", "plan"],
    queryFn: async () => {
      const { data, error } = await api.GET("/billing/plan");
      if (error) throw error;
      return data;
    },
  });

  return (
    <div className="flex items-center gap-3 border-t border-sidebar-border px-4 py-4">
      <UserButton />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-medium text-white">
          {user?.fullName ?? user?.primaryEmailAddress?.emailAddress ?? t("accountFallback")}
        </span>
        {planQuery.data && (
          <span className="text-xs text-white/60">{PLAN_LABELS[planQuery.data.plan]}</span>
        )}
      </div>
    </div>
  );
}

function MobileTopBar({ pathname, t }: { pathname: string; t: ReturnType<typeof useTranslations> }) {
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between bg-sidebar px-4 lg:hidden">
      <Link href="/dashboard" className="flex items-center gap-2 text-white">
        <span className="flex size-7 items-center justify-center rounded-md bg-gradient-brand">
          <BookOpen className="size-3.5" aria-hidden />
        </span>
        <span className="font-brand text-base font-semibold">StudyMate</span>
      </Link>

      <div className="flex items-center gap-2">
        <ThemeToggle />
        <LanguageSwitcher />
        <UserButton />
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="outline"
                size="icon"
                className="border-white/20 bg-transparent text-white hover:bg-white/10"
                aria-label={t("menu")}
              >
                <MenuIcon className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end">
            {NAV_ITEMS.map((item) => {
              const active = isNavItemActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <DropdownMenuLinkItem
                  key={item.href}
                  aria-current={active ? "page" : undefined}
                  className={active ? "bg-muted font-medium" : undefined}
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
    </header>
  );
}

/**
 * App shell v2 (docs/studymate-design-prompt.md) — a fixed, permanently-dark left
 * sidebar (brand, nav, usage widget, profile row) replaces the old top navbar on
 * `lg`+ screens; below `lg` it collapses into a slim dark top bar + dropdown, the same
 * collapse pattern the previous shell used. `ThemeToggle`/`LanguageSwitcher` live in
 * the CONTENT pane's utility row (desktop) or the mobile top bar — the design prompt's
 * sidebar content list doesn't mention them, and both render with the general
 * `--background`/`--border` theme tokens (light OR dark, whichever the app is in),
 * which would look wrong sitting inside a sidebar pinned to ITS OWN separate dark
 * tokens regardless of app theme — keeping them out of the sidebar avoids needing a
 * dark-context-specific variant of either shared component.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("Nav");

  return (
    <div className="min-h-screen bg-background">
      <MobileTopBar pathname={pathname} t={t} />

      <aside
        className={cn(
          "fixed inset-y-0 left-0 hidden flex-col bg-sidebar text-sidebar-foreground lg:flex",
          SIDEBAR_WIDTH_CLASS,
        )}
      >
        <BrandMark />
        <SidebarNav pathname={pathname} t={t} />
        <SidebarUsageWidget />
        <div className="flex-1" />
        <SidebarProfile />
      </aside>

      <div className="lg:pl-[236px]">
        {/* Desktop-only utility row (theme + language) — mobile gets the same
            controls inside MobileTopBar instead, not duplicated here. */}
        <div className="hidden items-center justify-end gap-2 px-12 pt-6 lg:flex">
          <ThemeToggle />
          <LanguageSwitcher />
        </div>

        <main className="mx-auto max-w-[920px] px-6 py-8 sm:px-12">{children}</main>
      </div>
    </div>
  );
}
