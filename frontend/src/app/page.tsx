"use client";

import { Show } from "@clerk/nextjs";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { BookOpen, FolderKanban, Layers, ListChecks, MessageSquareQuote } from "lucide-react";
import { PlanCard } from "@/components/plan-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PLAN_LABELS } from "@/lib/planLimits";

// Distinct tint per feature card so the 4-up grid reads as visually varied, not one
// repeated color — matching the design prompt's "different accent color per card"
// ask for this page specifically (the working app's cards stay on semantic tokens;
// this marketing page is the one place a small fixed decorative set is appropriate,
// same reasoning already established for lib/subjectBadgeTint.ts).
const FEATURES = [
  {
    key: "cited",
    icon: MessageSquareQuote,
    tint: "bg-teal-50 text-teal-600 dark:bg-teal-500/15 dark:text-teal-300",
  },
  {
    key: "flashcards",
    icon: Layers,
    tint: "bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300",
  },
  {
    key: "quizzes",
    icon: ListChecks,
    tint: "bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
  },
  {
    key: "organization",
    icon: FolderKanban,
    tint: "bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300",
  },
] as const;

const STEP_KEYS = ["step1", "step2", "step3"] as const;

function BrandMark() {
  return (
    <Link href="/" className="flex items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-lg bg-gradient-brand text-white">
        <BookOpen className="size-4" aria-hidden />
      </span>
      <span className="font-brand text-lg font-semibold">StudyMate</span>
    </Link>
  );
}

export default function Home() {
  const t = useTranslations("Landing");
  const tNav = useTranslations("Nav");
  const freeFeatures = t.raw("pricing.freeFeatures") as string[];
  const proFeatures = t.raw("pricing.proFeatures") as string[];
  const businessFeatures = t.raw("pricing.businessFeatures") as string[];

  return (
    <div>
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <BrandMark />
          <nav className="hidden items-center gap-6 text-sm font-medium text-muted-foreground sm:flex">
            <a href="#features" className="hover:text-foreground">
              {t("nav.features")}
            </a>
            <a href="#how" className="hover:text-foreground">
              {t("nav.howItWorks")}
            </a>
            <a href="#pricing" className="hover:text-foreground">
              {t("nav.pricing")}
            </a>
          </nav>
          <Show
            when="signed-in"
            fallback={
              <div className="flex items-center gap-3">
                <Link
                  href="/sign-in"
                  className="text-sm font-medium text-muted-foreground hover:text-foreground"
                >
                  {t("nav.signIn")}
                </Link>
                <Button
                  size="sm"
                  nativeButton={false}
                  render={<Link href="/sign-up">{t("nav.getStarted")}</Link>}
                />
              </div>
            }
          >
            <Button
              size="sm"
              nativeButton={false}
              render={<Link href="/dashboard">{tNav("dashboard")}</Link>}
            />
          </Show>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pt-16 pb-20 sm:px-6 sm:pt-24 lg:px-8">
        <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-2">
          <div>
            <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              {t("hero.eyebrow")}
            </span>
            <h1 className="mt-4 text-3xl font-semibold sm:text-4xl lg:text-5xl">
              {t("hero.headline")}
            </h1>
            <p className="mt-4 max-w-md text-muted-foreground">{t("hero.subheadline")}</p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Show
                when="signed-in"
                fallback={
                  <Button
                    nativeButton={false}
                    render={<Link href="/sign-up">{t("ctaGetStartedFree")}</Link>}
                  />
                }
              >
                <Button nativeButton={false} render={<Link href="/dashboard">{tNav("dashboard")}</Link>} />
              </Show>
              <Button variant="outline" nativeButton={false} render={<a href="#how">{t("hero.ctaSecondary")}</a>} />
            </div>
          </div>

          {/* A simplified, static illustration of the real dashboard — not real data,
              just enough visual shape (sidebar + a couple of stat tiles) for a visitor
              to see what the product looks like before signing up. */}
          <div className="rounded-2xl border border-border bg-card p-2 shadow-md">
            <div className="mb-2 flex items-center gap-1.5 px-2 pt-1">
              <span className="size-2.5 rounded-full bg-destructive/40" />
              <span className="size-2.5 rounded-full bg-warning/40" />
              <span className="size-2.5 rounded-full bg-success/40" />
            </div>
            <div className="flex overflow-hidden rounded-xl border border-border">
              <div className="hidden w-16 shrink-0 flex-col gap-3 bg-sidebar p-3 sm:flex">
                <span className="size-5 rounded-md bg-gradient-brand" />
                <span className="h-2 w-full rounded-full bg-white/20" />
                <span className="h-2 w-2/3 rounded-full bg-white/10" />
                <span className="h-2 w-2/3 rounded-full bg-white/10" />
              </div>
              <div className="flex-1 bg-background p-4">
                <div className="mb-3 h-3 w-24 rounded-full bg-muted" />
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-border bg-card p-3">
                    <p className="text-xs text-muted-foreground">{t("hero.previewDocuments")}</p>
                    <p className="text-lg font-bold text-success">3/10</p>
                  </div>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <p className="text-xs text-muted-foreground">{t("hero.previewFlashcardsDue")}</p>
                    <p className="text-lg font-bold text-warning">4</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="mb-10 text-center text-2xl font-semibold">{t("how.title")}</h2>
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
          {STEP_KEYS.map((key, index) => (
            <div key={key} className="flex flex-col items-center text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-gradient-brand text-sm font-bold text-white">
                {index + 1}
              </span>
              <p className="mt-4 font-medium">{t(`how.${key}Title`)}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t(`how.${key}Body`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="mb-10 text-center text-2xl font-semibold">{t("features.title")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ key, icon: Icon, tint }) => (
            <Card key={key} interactive className="h-full">
              <div className="flex h-full flex-col gap-3 p-5">
                <span className={`flex size-9 items-center justify-center rounded-[9px] ${tint}`}>
                  <Icon className="size-4" aria-hidden />
                </span>
                <p className="font-medium">{t(`features.${key}Title`)}</p>
                <p className="text-sm text-muted-foreground">{t(`features.${key}Body`)}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="mb-10 text-center text-2xl font-semibold">{t("pricing.title")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <PlanCard
            name={PLAN_LABELS.free}
            price="$0"
            priceSuffix=""
            description={t("pricing.freeDescription")}
            features={freeFeatures}
            ctaLabel={t("ctaGetStartedFree")}
            ctaHref="/sign-up"
          />
          <PlanCard
            name={PLAN_LABELS.pro}
            price="$20"
            priceSuffix={t("pricing.perMonth")}
            description={t("pricing.proDescription")}
            features={proFeatures}
            ctaLabel={t("pricing.proCta")}
            ctaHref="/sign-up?plan=pro"
            popular
            popularLabel={t("pricing.popularBadge")}
          />
          <PlanCard
            name={PLAN_LABELS.business}
            price="$100"
            priceSuffix={t("pricing.perMonth")}
            description={t("pricing.businessDescription")}
            features={businessFeatures}
            ctaLabel={t("pricing.businessCta")}
            ctaHref="/sign-up?plan=business"
          />
        </div>
      </section>

      {/* Closing CTA — the one place a full gradient fill is appropriate, per the
          design prompt's landing-page exception (never on the working app screens). */}
      <section className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:px-8">
        <div className="rounded-2xl bg-gradient-brand px-6 py-12 text-center text-white sm:px-12">
          <h2 className="text-2xl font-semibold">{t("closing.title")}</h2>
          <p className="mt-2 text-white/85">{t("closing.body")}</p>
          <Button
            className="mt-6 bg-white text-primary hover:bg-white/90"
            nativeButton={false}
            render={<Link href="/sign-up">{t("ctaGetStartedFree")}</Link>}
          />
        </div>
      </section>

      <footer className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:px-6 lg:px-8">
        <p>{t("footer.copyright", { year: new Date().getFullYear() })}</p>
        <p>
          {t("footer.signInPrompt")}{" "}
          <Link href="/sign-in" className="font-medium text-primary hover:underline">
            {t("nav.signIn")}
          </Link>
        </p>
      </footer>
    </div>
  );
}
