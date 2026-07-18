"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ErrorState } from "@/components/error-state";
import { PlanCard } from "@/components/plan-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageMeters } from "@/components/usage-meters";
import { useApiClient } from "@/lib/api/useApiClient";
import { PLAN_LABELS } from "@/lib/planLimits";
import type { components } from "@/lib/api/schema";

type Plan = components["schemas"]["Plan"];

// Ordered comparison grid — every plan, not just upgrade targets, so a Pro user can
// still see what Business unlocks and a Free user sees Business too, not just the
// next tier up. The design prompt's "fuller comparison layout" is this: the billing
// page is the one place all three plans + their full feature lists are shown side by
// side (the dashboard's condensed UsageStatCard grid never repeats this).
const PLAN_ORDER: Plan[] = ["free", "pro", "business"];

const PLAN_PRICE: Record<Plan, { price: string; suffix: string }> = {
  free: { price: "$0", suffix: "" },
  pro: { price: "$20", suffix: "/month" },
  business: { price: "$100", suffix: "/month" },
};

// Mirrors billing.service.LIMITS (backend) — stated here as plain feature bullets
// rather than re-deriving them from `plan.limits`, since a card must describe EVERY
// plan's caps, not just the caller's own current one.
const PLAN_FEATURES: Record<Plan, string[]> = {
  free: ["3 subjects", "10 documents per subject", "20 generations per day"],
  pro: ["50 subjects", "200 documents per subject", "200 generations per day"],
  business: ["Unlimited subjects", "Unlimited documents", "Unlimited generations"],
};

const POPULAR_PLAN: Plan = "pro";

// Only plans "above" the current one can actually be checked out — Free is never sold
// (the backend 400s on it) and a plan can't "upgrade" to itself or downward here.
const CHECKOUT_TARGETS: Record<Plan, Exclude<Plan, "free">[]> = {
  free: ["pro", "business"],
  pro: ["business"],
  business: [],
};

export default function BillingPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [justUpgraded, setJustUpgraded] = useState(false);

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
    onSuccess: (data) => {
      // Hand off to Polar's hosted checkout page.
      window.location.href = data.checkout_url;
    },
  });

  const plan = planQuery.data;
  const checkoutTargets = plan ? CHECKOUT_TARGETS[plan.plan] : [];

  return (
    <div>
      <h1 className="mb-6 text-[22px] font-semibold">Plan &amp; billing</h1>

      {justUpgraded && (
        <div className="mb-6 rounded-lg border border-success/40 bg-success/5 p-4 text-sm">
          Thanks! Your payment went through. Your new plan is being activated and should
          appear here in a moment.
        </div>
      )}

      {planQuery.isLoading && (
        <div role="status" aria-label="Loading plan">
          <Skeleton className="mb-6 h-28 w-full rounded-xl" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        </div>
      )}
      {planQuery.isError && (
        <ErrorState
          message="Couldn't load your plan."
          retryLabel="Retry"
          onRetry={() => planQuery.refetch()}
        />
      )}

      {plan && (
        <div className="flex flex-col gap-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2 text-base">
                <span>Current plan</span>
                <span className="text-primary">{PLAN_LABELS[plan.plan]}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <UsageMeters plan={plan} />
              <p className="mt-4 text-xs text-muted-foreground">
                Documents are capped per subject
                {plan.limits.max_documents_per_subject !== null
                  ? ` (${plan.limits.max_documents_per_subject} each on ${PLAN_LABELS[plan.plan]})`
                  : " (unlimited on your plan)"}
                .
              </p>
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-3 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
              Compare plans
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {PLAN_ORDER.map((candidate) => {
                const isCurrent = candidate === plan.plan;
                const { price, suffix } = PLAN_PRICE[candidate];
                const canCheckout = checkoutTargets.includes(candidate as Exclude<Plan, "free">);
                return (
                  <PlanCard
                    key={candidate}
                    name={PLAN_LABELS[candidate]}
                    price={price}
                    priceSuffix={suffix}
                    features={PLAN_FEATURES[candidate]}
                    popular={candidate === POPULAR_PLAN}
                    popularLabel="Most popular"
                    isCurrent={isCurrent}
                    ctaLabel={
                      isCurrent
                        ? "Current plan"
                        : checkout.isPending && checkout.variables === candidate
                          ? "Redirecting…"
                          : canCheckout
                            ? `Upgrade to ${PLAN_LABELS[candidate]}`
                            : "Not available"
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
            <p className="text-sm text-destructive">Couldn&apos;t start checkout. Please try again.</p>
          )}
        </div>
      )}
    </div>
  );
}
