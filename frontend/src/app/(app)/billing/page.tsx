"use client";

import { useOrganization } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ErrorState } from "@/components/error-state";
import { PlanCard } from "@/components/plan-card";
import { ReferralCard } from "@/components/referral-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageMeters } from "@/components/usage-meters";
import { captureEvent } from "@/lib/analytics";
import { useApiClient } from "@/lib/api/useApiClient";
import { PLAN_LABELS } from "@/lib/planLimits";
import { canShowTeamUpgrade } from "@/lib/teamUpgrade";
import type { components } from "@/lib/api/schema";

type Plan = components["schemas"]["Plan"];

// Ordered comparison grid — every plan, not just upgrade targets, so a Pro user can
// still see what Business unlocks and a Free user sees Business too, not just the
// next tier up. The design prompt's "fuller comparison layout" is this: the billing
// page is the one place all three plans + their full feature lists are shown side by
// side (the dashboard's condensed UsageStatCard grid never repeats this).
const PLAN_ORDER: Plan[] = ["free", "pro", "business"];

// "team" isn't in PLAN_ORDER (it's not a self-serve individual-checkout plan — see the
// Team Plan card below), so these entries are never actually read at runtime. They
// exist only so these Records stay exhaustive over `Plan` now that the backend's enum
// includes it (an org member's effective plan can read back as "team").
const PLAN_PRICE: Record<Plan, string> = {
  free: "$0",
  pro: "$20",
  business: "$100",
  team: "$10",
};

// Mirrors the marketing landing page's plan cards — same three plans, same caps — so
// the feature bullets are read from the shared Landing.pricing.*Features catalog keys
// instead of duplicating the copy here.
const PLAN_FEATURES_KEY: Record<Plan, string> = {
  free: "Landing.pricing.freeFeatures",
  pro: "Landing.pricing.proFeatures",
  business: "Landing.pricing.businessFeatures",
  team: "Landing.pricing.businessFeatures",
};

const POPULAR_PLAN: Plan = "pro";

// Only plans "above" the current one can actually be checked out — Free is never sold
// (the backend 400s on it) and a plan can't "upgrade" to itself or downward here.
const CHECKOUT_TARGETS: Record<Plan, Exclude<Plan, "free">[]> = {
  free: ["pro", "business"],
  pro: ["business"],
  business: [],
  team: [],
};

export default function BillingPage() {
  const t = useTranslations();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [justUpgraded, setJustUpgraded] = useState(false);
  const { organization, membership } = useOrganization();

  const planQuery = useQuery({
    queryKey: ["billing", "plan"],
    queryFn: async () => {
      const { data, error } = await api.GET("/billing/plan");
      if (error) throw error;
      return data;
    },
  });

  // Polar redirects back here with ?upgraded=1 after a successful checkout. The plan
  // change lands via an async webhook, so it may not be reflected yet — show a note and
  // refetch (rather than reading useSearchParams, which would force a Suspense boundary).
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("upgraded") === "1") {
      setJustUpgraded(true);
      queryClient.invalidateQueries({ queryKey: ["billing", "plan"] });
    }
  }, [queryClient]);

  const checkout = useMutation({
    mutationFn: async (targetPlan: Exclude<Plan, "free">) => {
      const { data, error } = await api.POST("/billing/checkout", {
        body: {
          plan: targetPlan,
          success_url: `${window.location.origin}/billing?upgraded=1`,
        },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: (data, targetPlan) => {
      captureEvent("checkoutStarted", { plan: targetPlan });
      // Hand off to Polar's hosted checkout page.
      window.location.href = data.checkout_url;
    },
  });

  const teamCheckout = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/billing/team-checkout", {
        body: {
          success_url: `${window.location.origin}/billing?upgraded=1`,
        },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => {
      captureEvent("checkoutStarted", { plan: "team" });
      // Hand off to Polar's hosted checkout page (same mechanism as the individual plan).
      window.location.href = data.checkout_url;
    },
  });

  const plan = planQuery.data;
  const checkoutTargets = plan ? CHECKOUT_TARGETS[plan.plan] : [];
  const showTeamUpgrade = canShowTeamUpgrade(organization != null, membership?.role);

  return (
    <div>
      <h1 className="mb-6 text-[22px] font-semibold">{t("Billing.heading")}</h1>

      {justUpgraded && (
        <div className="mb-6 rounded-lg border border-success/40 bg-success/5 p-4 text-sm">
          {t("Billing.upgradedNotice")}
        </div>
      )}

      {planQuery.isLoading && (
        <div role="status" aria-label={t("Billing.loadingAriaLabel")}>
          <Skeleton className="mb-6 h-28 w-full rounded-xl" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        </div>
      )}
      {planQuery.isError && (
        <ErrorState
          message={t("Billing.loadError")}
          retryLabel={t("Common.retry")}
          onRetry={() => planQuery.refetch()}
        />
      )}

      {plan && (
        <div className="flex flex-col gap-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2 text-base">
                <span>{t("Billing.currentPlan")}</span>
                <span className="text-primary">{PLAN_LABELS[plan.plan]}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <UsageMeters plan={plan} />
              <p className="mt-4 text-xs text-muted-foreground">
                {t("Billing.documentsCapNote")}
                {plan.limits.max_documents_per_subject !== null
                  ? t("Billing.documentsCapNoteWithLimit", {
                      cap: plan.limits.max_documents_per_subject,
                      plan: PLAN_LABELS[plan.plan],
                    })
                  : t("Billing.documentsCapNoteUnlimited")}
                .
              </p>
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-3 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
              {t("Billing.comparePlans")}
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {PLAN_ORDER.map((candidate) => {
                const isCurrent = candidate === plan.plan;
                const canCheckout = checkoutTargets.includes(candidate as Exclude<Plan, "free">);
                return (
                  <PlanCard
                    key={candidate}
                    name={PLAN_LABELS[candidate]}
                    price={PLAN_PRICE[candidate]}
                    priceSuffix={candidate === "free" ? "" : t("Landing.pricing.perMonth")}
                    features={t.raw(PLAN_FEATURES_KEY[candidate]) as string[]}
                    popular={candidate === POPULAR_PLAN}
                    popularLabel={t("Landing.pricing.popularBadge")}
                    isCurrent={isCurrent}
                    ctaLabel={
                      isCurrent
                        ? t("Billing.currentPlanCta")
                        : checkout.isPending && checkout.variables === candidate
                          ? t("Billing.redirecting")
                          : canCheckout
                            ? t("Billing.upgradeTo", { plan: PLAN_LABELS[candidate] })
                            : t("Billing.notAvailable")
                    }
                    ctaDisabled={!canCheckout || checkout.isPending}
                    onCta={
                      canCheckout
                        ? () => checkout.mutate(candidate as Exclude<Plan, "free">)
                        : undefined
                    }
                  />
                );
              })}
            </div>
          </div>

          {checkout.isError && (
            <p className="text-sm text-destructive">{t("Billing.checkoutError")}</p>
          )}

          {showTeamUpgrade && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("Billing.teamPlan.title")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-2xl font-bold">
                  {t("Billing.teamPlan.price")}
                </p>
                <p className="text-sm text-muted-foreground">{t("Billing.teamPlan.benefit")}</p>
                <Button
                  className="w-full sm:w-auto"
                  disabled={teamCheckout.isPending}
                  onClick={() => teamCheckout.mutate()}
                >
                  {teamCheckout.isPending ? t("Billing.redirecting") : t("Billing.teamPlan.cta")}
                </Button>
                {teamCheckout.isError && (
                  <p className="text-sm text-destructive">{t("Billing.checkoutError")}</p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <div className="mt-8">
        <ReferralCard />
      </div>
    </div>
  );
}
