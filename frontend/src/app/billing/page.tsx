"use client";

import { UserButton } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageMeters } from "@/components/usage-meters";
import { useApiClient } from "@/lib/api/useApiClient";
import { PLAN_LABELS, PLAN_PRICES } from "@/lib/planLimits";
import type { components } from "@/lib/api/schema";

type Plan = components["schemas"]["Plan"];

// Upgrade targets available from each plan: only plans "above" the current one. Business
// is the top tier, so it offers nothing further. Free is never listed as a target — it's
// the absence of a paid plan and can't be checked out (the backend 400s on it anyway).
const UPGRADE_OPTIONS: Record<Plan, Exclude<Plan, "free">[]> = {
  free: ["pro", "business"],
  pro: ["business"],
  business: [],
};

const PLAN_BLURB: Record<Exclude<Plan, "free">, string> = {
  pro: "50 subjects · 200 documents each · 200 generations/day",
  business: "Unlimited subjects, documents, and generations",
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
  const upgradeTargets = plan ? UPGRADE_OPTIONS[plan.plan] : [];

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <div className="mb-6 flex items-center justify-between gap-2">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Dashboard
        </Link>
        <UserButton />
      </div>

      <h1 className="mb-6 text-2xl font-semibold">Plan &amp; billing</h1>

      {justUpgraded && (
        <div className="mb-6 rounded-lg border border-success/40 bg-success/5 p-4 text-sm">
          Thanks! Your payment went through. Your new plan is being activated and should
          appear here in a moment.
        </div>
      )}

      {planQuery.isLoading && <p>Loading…</p>}
      {planQuery.isError && (
        <p className="text-destructive">Couldn&apos;t load your plan.</p>
      )}

      {plan && (
        <div className="flex flex-col gap-6">
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

          {upgradeTargets.length > 0 ? (
            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-medium text-muted-foreground">
                {plan.plan === "free" ? "Upgrade" : "Change plan"}
              </h2>
              {upgradeTargets.map((target) => (
                <Card key={target}>
                  <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="font-medium">
                        {PLAN_LABELS[target]}{" "}
                        <span className="text-muted-foreground">· {PLAN_PRICES[target]}</span>
                      </p>
                      <p className="text-sm text-muted-foreground">{PLAN_BLURB[target]}</p>
                    </div>
                    <Button
                      className="shrink-0"
                      disabled={checkout.isPending}
                      onClick={() => checkout.mutate(target)}
                    >
                      {checkout.isPending ? "Redirecting…" : `Upgrade to ${PLAN_LABELS[target]}`}
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              You&apos;re on the top plan — everything is unlimited.
            </p>
          )}

          {checkout.isError && (
            <p className="text-destructive text-sm">
              Couldn&apos;t start checkout. Please try again.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
