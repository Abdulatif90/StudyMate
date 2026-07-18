import type { components } from "@/lib/api/schema";

type Plan = components["schemas"]["Plan"];
type PlanRead = components["schemas"]["PlanRead"];

export const PLAN_LABELS: Record<Plan, string> = {
  free: "Free",
  pro: "Pro",
  business: "Business",
};

export interface UsageMeter {
  key: "subjects" | "generations";
  label: string;
  used: number;
  /** `null` means unlimited (Business) — there's no bar to draw. */
  cap: number | null;
  unlimited: boolean;
  /** 0–100, rounded and clamped. `0` when unlimited (a bar isn't meaningful). */
  percent: number;
  /** `true` once a finite cap is fully consumed. Drives the "at limit" styling —
   * we never rely on `percent === 100` for this, since rounding can reach 100 early. */
  atLimit: boolean;
}

/** Percentage of a cap consumed, rounded to a whole number and clamped to 0–100.
 * Unlimited (`null`) or a non-positive cap has no meaningful fill, so it returns 0. */
export function meterPercent(used: number, cap: number | null): number {
  if (cap === null || cap <= 0) return 0;
  const pct = Math.round((used / cap) * 100);
  return Math.min(100, Math.max(0, pct));
}

/** The account-wide usage meters shown on the billing page.
 *
 * Only the two caps that have a single account-wide number live here — subjects and
 * daily generations. `max_documents_per_subject` is deliberately absent: it's a
 * *per-subject* cap with no one account-wide count, so it's stated as a rule elsewhere
 * (and enforced per-subject on upload), not metered here. */
export function usageMeters(plan: PlanRead): UsageMeter[] {
  const build = (
    key: UsageMeter["key"],
    label: string,
    used: number,
    cap: number | null,
  ): UsageMeter => ({
    key,
    label,
    used,
    cap,
    unlimited: cap === null,
    percent: meterPercent(used, cap),
    atLimit: cap !== null && used >= cap,
  });

  return [
    build("subjects", "Subjects", plan.usage.subjects, plan.limits.max_subjects),
    build(
      "generations",
      "Quiz/flashcard generations today",
      plan.usage.generations_today,
      plan.limits.max_generations_per_day,
    ),
  ];
}
