"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { CheckCircle2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiClient } from "@/lib/api/useApiClient";
import { telegramConnectState } from "@/lib/telegramConnectState";

/**
 * Dashboard "Connect Telegram" card — one-tap linking, not the manual "type /start
 * <code>" flow: an `<a target="_blank">` whose `href` is a real deep link
 * (`https://t.me/<bot>?start=<code>`), so tapping it is a genuine user-gesture
 * navigation that opens Telegram reliably (no popup-blocker risk from a
 * click-then-fetch-then-`window.open` flow).
 *
 * The link code is minted as soon as we know the account is unlinked (on mount, not on
 * click) so the anchor's `href` is already populated by the time the user taps it. Codes
 * are short-lived/single-use and cheap to issue, so a code that's never redeemed (the
 * user navigates away first) is fine to let expire unused.
 *
 * After the user finishes in Telegram, they refresh this page to see the connected
 * state — no live push/poll this increment (noted as a known follow-up, not a bug).
 */
export function TelegramConnectCard() {
  const t = useTranslations("Dashboard");
  const api = useApiClient();

  const statusQuery = useQuery({
    queryKey: ["telegram", "status"],
    queryFn: async () => {
      const { data, error } = await api.GET("/telegram/status");
      if (error) throw error;
      return data;
    },
  });

  const linked = statusQuery.data?.linked;

  const linkQuery = useQuery({
    queryKey: ["telegram", "link"],
    queryFn: async () => {
      const { data, error } = await api.POST("/telegram/link");
      if (error) throw error;
      return data;
    },
    enabled: linked === false,
    staleTime: Infinity,
  });

  const state = telegramConnectState({
    statusLoading: statusQuery.isLoading,
    statusError: statusQuery.isError,
    linked,
    deepLink: linkQuery.data?.deep_link,
  });

  if (state.kind === "error") return null; // non-critical widget — fail quiet, dashboard still works

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("telegramCardTitle")}</CardTitle>
        <CardDescription>{t("telegramCardDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {state.kind === "loading" ? (
          <Skeleton className="h-9 w-full max-w-56 rounded-lg" />
        ) : state.kind === "connected" ? (
          <div className="flex items-center gap-2 rounded-lg bg-success-bg px-3 py-2 text-sm text-success">
            <CheckCircle2 className="size-4 shrink-0" aria-hidden />
            <span>
              {t("telegramConnected")} — {t("telegramConnectedHandle")}
            </span>
          </div>
        ) : state.deepLink ? (
          <Button
            nativeButton={false}
            render={
              <a href={state.deepLink} target="_blank" rel="noopener noreferrer">
                <Send className="size-4" aria-hidden />
                {t("telegramConnect")}
              </a>
            }
          />
        ) : (
          <Button disabled>
            <Send className="size-4" aria-hidden />
            {t("telegramConnect")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
