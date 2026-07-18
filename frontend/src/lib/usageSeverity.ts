import type { UsageMeter } from "@/lib/planLimits";

export type UsageSeverity = "normal" | "warning" | "atLimit";

/** Escalation point (of the cap) at which a proactive usage hint turns to warning
 * styling — deliberately BEFORE the cap is actually hit (unlike `UsageMeter.atLimit`,
 * which only fires once it's fully consumed), so a Free user sees the limit coming
 * instead of only learning about it via the reactive 402 `<UpgradePrompt>`. */
const WARNING_THRESHOLD_PERCENT = 80;

/** Severity classification for a proactive usage hint (e.g. "2 of 3 subjects used"
 * shown near the create-subject action). Returns `null` for an unlimited meter
 * (Business) — there's no cap to warn about. Text formatting is left to the caller
 * (via next-intl `t(...)`), this only classifies how urgent it is. */
export function usageSeverity(meter: UsageMeter): UsageSeverity | null {
  if (meter.unlimited) return null;
  if (meter.atLimit) return "atLimit";
  if (meter.percent >= WARNING_THRESHOLD_PERCENT) return "warning";
  return "normal";
}
