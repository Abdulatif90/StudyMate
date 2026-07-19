"use client";

import { useAuth } from "@clerk/nextjs";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { toast } from "@/components/ui/toast";
import { useApiClient } from "@/lib/api/useApiClient";
import { PENDING_REFERRAL_KEY } from "@/lib/referral";

/**
 * Once the user is authenticated, redeem any referral code captured before sign-in
 * (<ReferralCapture/> stashed it in localStorage). Fires at most once per session for a
 * given pending code.
 *
 * Mounted in the (app) route-group layout, so it only runs on authenticated pages —
 * "the first authenticated load" the referral flow needs. The response is handled
 * quietly: a 204 success thanks the user via a toast; the expected 409 ("already
 * referred") and the other rejections (unknown code / self-referral) are silent no-ops
 * the referred user never needs to see. The pending code is cleared on any definitive
 * server response so it isn't retried forever; a genuine network failure leaves it in
 * place to retry on a later load.
 */
export function ReferralRedeemer() {
  const { isSignedIn } = useAuth();
  const api = useApiClient();
  const t = useTranslations("Referral");
  const attempted = useRef(false);

  useEffect(() => {
    if (!isSignedIn || attempted.current) return;

    let code: string | null = null;
    try {
      code = window.localStorage.getItem(PENDING_REFERRAL_KEY);
    } catch {
      return; // localStorage unavailable — nothing to redeem.
    }
    if (!code) return;

    attempted.current = true;

    void (async () => {
      try {
        const { response } = await api.POST("/referral/redeem", { body: { code } });
        if (response.ok) {
          toast.success(t("redeemedToast"));
        }
        // Any definitive response (2xx or a 4xx like 409/404/400) means the code was
        // seen by the server — clear it so it isn't reattempted on every load.
        try {
          window.localStorage.removeItem(PENDING_REFERRAL_KEY);
        } catch {
          // ignore — clearing is best-effort.
        }
      } catch {
        // The request never reached the server (offline / transient). Keep the pending
        // code and reset the guard so a later mount can retry.
        attempted.current = false;
      }
    })();
  }, [isSignedIn, api, t]);

  return null;
}
