import type { components } from "@/lib/api/schema";
import type { badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

type DocumentStatus = components["schemas"]["DocumentStatus"];
type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

export function documentStatusVariant(status: DocumentStatus): BadgeVariant {
  if (status === "ready") return "default";
  if (status === "failed") return "destructive";
  return "secondary";
}
