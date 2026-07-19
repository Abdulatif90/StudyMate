"use client";

import { useEffect } from "react";
import { parseRefParam, PENDING_REFERRAL_KEY } from "@/lib/referral";

/**
 * Captures a `?ref=CODE` referral param on first load and stashes it in localStorage,
 * so it survives the Clerk sign-in/sign-up redirect (which drops query params). The
 * actual redemption happens later, once authenticated, in <ReferralRedeemer/>.
 *
 * Mounted globally (in Providers) rather than only on /sign-up, so a ref link that lands
 * on any page is still captured. Best-effort: a malformed code is ignored (parseRefParam
 * validates), and localStorage being unavailable (private mode) is a silent no-op.
 */
export function ReferralCapture() {
  useEffect(() => {
    const code = parseRefParam(window.location.search);
    if (!code) return;
    try {
      window.localStorage.setItem(PENDING_REFERRAL_KEY, code);
    } catch {
      // localStorage disabled/unavailable — capture is best-effort, never fatal.
    }
  }, []);

  return null;
}
