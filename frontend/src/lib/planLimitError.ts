import type { components } from "@/lib/api/schema";

type Plan = components["schemas"]["Plan"];

export type PlanLimitKind =
  | "subjects"
  | "documents_per_subject"
  | "generations_per_day";

export interface PlanLimitError {
  limit: PlanLimitKind;
  plan: Plan;
  cap: number;
  /** Human-readable message straight from the backend (already names the limit + cap). */
  detail: string;
}

/**
 * Recognise a plan-limit rejection (HTTP 402) from an openapi-fetch response.
 *
 * The 402 body is `{ detail, limit, plan, cap }` (see the app-wide handler in
 * `backend/app/main.py`). openapi-typescript doesn't type it — FastAPI only documents
 * 201/422 for these routes — so the body arrives untyped and we validate its shape here
 * rather than casting blindly. Returns the structured error, or `null` when the status
 * isn't 402 or the body doesn't carry the expected fields (any other failure stays a
 * generic error at the call site).
 */
export function parsePlanLimitError(
  status: number,
  body: unknown,
): PlanLimitError | null {
  if (status !== 402) return null;
  if (typeof body !== "object" || body === null) return null;

  const b = body as Record<string, unknown>;
  if (
    typeof b.limit !== "string" ||
    typeof b.plan !== "string" ||
    typeof b.cap !== "number"
  ) {
    return null;
  }

  return {
    limit: b.limit as PlanLimitKind,
    plan: b.plan as Plan,
    cap: b.cap,
    detail:
      typeof b.detail === "string" && b.detail.length > 0
        ? b.detail
        : "You've reached your plan limit. Upgrade your plan to continue.",
  };
}
