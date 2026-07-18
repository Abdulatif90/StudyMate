import { cn } from "@/lib/utils";
import { usageSeverity } from "@/lib/usageSeverity";
import type { UsageMeter } from "@/lib/planLimits";

interface UsageHintProps {
  meter: UsageMeter;
  /** Already-translated "X of Y … used" text — this component has no copy of its own
   * to translate, same reasoning as `EmptyState`/`ErrorState`. */
  text: string;
}

const SEVERITY_CLASS = {
  normal: "text-muted-foreground",
  warning: "text-warning",
  atLimit: "text-destructive",
} as const;

/** A small, PROACTIVE usage indicator ("2 of 3 subjects used") shown where the user is
 * about to consume a capped resource — distinct from the REACTIVE `<UpgradePrompt>`,
 * which only appears after a request is actually rejected with a 402. Renders nothing
 * for an unlimited meter (Business) or once the account has never been near the cap. */
export function UsageHint({ meter, text }: UsageHintProps) {
  const severity = usageSeverity(meter);
  if (severity === null) return null;
  return <p className={cn("text-xs", SEVERITY_CLASS[severity])}>{text}</p>;
}
