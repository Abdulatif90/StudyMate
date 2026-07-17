import { cn } from "@/lib/utils";
import { usageMeters } from "@/lib/planLimits";
import type { components } from "@/lib/api/schema";

type PlanRead = components["schemas"]["PlanRead"];

/** Usage bars for the account-wide caps ("2 of 3 subjects used"). Unlimited dimensions
 * (Business) show a count without a bar, since there's nothing to fill toward. The bar
 * is `role="img"` with an aria-label carrying the same "used of cap" text, so the meter
 * is never conveyed by the fill width alone. */
export function UsageMeters({ plan }: { plan: PlanRead }) {
  const meters = usageMeters(plan);

  return (
    <div className="flex flex-col gap-4">
      {meters.map((meter) => (
        <div key={meter.key} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-foreground">{meter.label}</span>
            <span
              className={cn(
                "text-muted-foreground",
                meter.atLimit && "font-medium text-destructive",
              )}
            >
              {meter.unlimited
                ? `${meter.used} · Unlimited`
                : `${meter.used} of ${meter.cap} used`}
            </span>
          </div>
          {!meter.unlimited && (
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`${meter.label}: ${meter.used} of ${meter.cap} used`}
            >
              <div
                className={cn(
                  "h-full rounded-full transition-all",
                  meter.atLimit ? "bg-destructive" : "bg-primary",
                )}
                style={{ width: `${meter.percent}%` }}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
