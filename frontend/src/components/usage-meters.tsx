import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { usageMeters } from "@/lib/planLimits";
import type { components } from "@/lib/api/schema";

type PlanRead = components["schemas"]["PlanRead"];

/** Usage bars for the account-wide caps ("2 of 3 subjects used"). Unlimited dimensions
 * (Business) show a count without a bar, since there's nothing to fill toward. The bar
 * is `role="img"` with an aria-label carrying the same "used of cap" text, so the meter
 * is never conveyed by the fill width alone. */
export function UsageMeters({ plan }: { plan: PlanRead }) {
  const t = useTranslations("Usage");
  const meters = usageMeters(plan);

  return (
    <div className="flex flex-col gap-4">
      {meters.map((meter) => (
        <div key={meter.key} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="text-foreground">{t(meter.key)}</span>
            <span
              className={cn(
                "text-muted-foreground",
                meter.atLimit && "font-medium text-destructive",
              )}
            >
              {meter.unlimited
                ? t("usedUnlimited", { used: meter.used })
                : t("usedOfCap", { used: meter.used, cap: meter.cap ?? 0 })}
            </span>
          </div>
          {!meter.unlimited && (
            <div
              className={cn(
                // Meter form (dataviz skill): the unfilled track is a lighter step of
                // the SAME ramp as the fill, not a neutral gray — so severity reads
                // across the whole bar, not just the filled portion.
                "h-2 w-full overflow-hidden rounded-full",
                meter.atLimit ? "bg-destructive/15" : "bg-primary/15",
              )}
              role="img"
              aria-label={t("meterAriaLabel", {
                label: t(meter.key),
                used: meter.used,
                cap: meter.cap ?? 0,
              })}
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
