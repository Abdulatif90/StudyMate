import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PlanCardProps {
  name: string;
  price: string;
  priceSuffix: string;
  features: string[];
  ctaLabel: string;
  onCta?: () => void;
  ctaDisabled?: boolean;
  /** Gets the 1.5px brand-colored border + the overlapping "Most popular" badge. */
  popular?: boolean;
  popularLabel?: string;
  /** The caller's own plan — CTA renders as a disabled `outline` button instead of the
   * brand-gradient primary one, since there's no action to take on your own plan. */
  isCurrent?: boolean;
}

export function PlanCard({
  name,
  price,
  priceSuffix,
  features,
  ctaLabel,
  onCta,
  ctaDisabled,
  popular = false,
  popularLabel,
  isCurrent = false,
}: PlanCardProps) {
  return (
    <Card className={cn("relative border", popular && "border-[1.5px] border-primary")}>
      {popular && popularLabel && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-brand px-3 py-1 text-xs font-semibold text-white shadow-sm">
          {popularLabel}
        </span>
      )}
      <CardContent className="flex h-full flex-col gap-4 py-6">
        <div>
          <p className="text-sm font-semibold">{name}</p>
          <p className="mt-1">
            <span className="text-2xl font-bold">{price}</span>
            <span className="text-sm text-muted-foreground">{priceSuffix}</span>
          </p>
        </div>
        <ul className="flex flex-1 flex-col gap-2">
          {features.map((feature) => (
            <li key={feature} className="flex items-start gap-2 text-sm">
              <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
              <span>{feature}</span>
            </li>
          ))}
        </ul>
        <Button
          className="w-full"
          variant={isCurrent ? "outline" : "default"}
          disabled={ctaDisabled || isCurrent}
          onClick={onCta}
        >
          {ctaLabel}
        </Button>
      </CardContent>
    </Card>
  );
}
