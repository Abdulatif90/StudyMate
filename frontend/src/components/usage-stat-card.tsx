import { AnimatedProgressBar } from "@/components/ui/animated-progress-bar";
import { Card, CardContent } from "@/components/ui/card";
import { usageSeverity } from "@/lib/usageSeverity";
import { cn } from "@/lib/utils";
import type { UsageMeter } from "@/lib/planLimits";

const VALUE_CLASS = {
  normal: "text-success",
  warning: "text-warning",
  atLimit: "text-warning",
} as const;

const FILL_CLASS = {
  normal: "bg-success-fill",
  warning: "bg-warning-fill",
  atLimit: "bg-warning-fill",
} as const;

/**
 * The dashboard's CONDENSED usage summary tile — label + bold value pair, colored
 * amber/green by how close to the cap it is, with a thin animated progress track
 * below. Deliberately just this much detail: the billing page shows the same data in
 * a fuller layout instead (design prompt's "don't duplicate the same detailed widget
 * across two pages" rule) — this component is dashboard-only by design, not reused
 * there. An unlimited meter (Business) reads as healthy/green — there's no cap to be
 * close to.
 */
export function UsageStatCard({ meter }: { meter: UsageMeter }) {
  const severity = usageSeverity(meter) ?? "normal";

  return (
    <Card>
      <CardContent className="flex flex-col gap-2 py-4">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {meter.label}
          </span>
          <span className={cn("text-base font-bold", VALUE_CLASS[severity])}>
            {meter.unlimited ? "∞" : `${meter.used}/${meter.cap}`}
          </span>
        </div>
        {!meter.unlimited && (
          <AnimatedProgressBar
            percent={meter.percent}
            trackClassName="h-1.5"
            fillClassName={FILL_CLASS[severity]}
          />
        )}
      </CardContent>
    </Card>
  );
}
