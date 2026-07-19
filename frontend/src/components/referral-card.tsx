"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { useApiClient } from "@/lib/api/useApiClient";
import { buildReferralShareUrl } from "@/lib/referral";

/**
 * "Refer a friend" card: shows the user's stable referral code and a copy-to-clipboard
 * share link (`/sign-up?ref=CODE`). Attribution only — no reward is granted yet (that's
 * a deferred increment), so the copy stays neutral about any bonus.
 */
export function ReferralCard() {
  const t = useTranslations("Referral");
  const api = useApiClient();
  const [copied, setCopied] = useState(false);

  const referralQuery = useQuery({
    queryKey: ["referral"],
    queryFn: async () => {
      const { data, error } = await api.GET("/referral");
      if (error) throw error;
      return data;
    },
  });

  const code = referralQuery.data?.code;
  const referredCount = referralQuery.data?.referred_count ?? 0;
  // window.location.origin is only available client-side; this whole component is a
  // client component, but guard anyway so it's safe under any render path.
  const shareUrl =
    code && typeof window !== "undefined"
      ? buildReferralShareUrl(window.location.origin, code)
      : "";

  async function handleCopy() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success(t("copiedToast"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t("copyError"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("heading")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-muted-foreground">{t("description")}</p>

        {referralQuery.isLoading && <Skeleton className="h-11 w-full rounded-lg" />}

        {referralQuery.isError && (
          <p className="text-sm text-destructive">{t("loadError")}</p>
        )}

        {code && (
          <>
            <div className="flex flex-col gap-2 sm:flex-row">
              <output
                aria-label={t("shareLinkAriaLabel")}
                className="min-w-0 flex-1 truncate rounded-lg border border-border bg-muted px-3 py-2 font-mono text-sm text-foreground"
              >
                {shareUrl}
              </output>
              <Button type="button" onClick={handleCopy} className="shrink-0">
                {copied ? t("copied") : t("copy")}
              </Button>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {t("referredCount", { count: referredCount })}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
