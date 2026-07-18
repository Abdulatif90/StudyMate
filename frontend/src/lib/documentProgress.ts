import type { components } from "@/lib/api/schema";
import type { badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

type DocumentStatusCounts = components["schemas"]["DocumentStatusCounts"];
type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

export interface DocumentStatusRow {
  key: "ready" | "pending" | "failed";
  count: number;
  variant: BadgeVariant; // same ready/pending/failed -> badge-variant mapping as
  // documentStatus.ts's documentStatusVariant (ready=default, failed=destructive,
  // pending=secondary), kept as a separate pure function here since this operates on
  // aggregated counts, not a single Document's status.
}

export function documentStatusRows(documents: DocumentStatusCounts): DocumentStatusRow[] {
  return [
    { key: "ready", count: documents.ready, variant: "default" },
    { key: "pending", count: documents.pending, variant: "secondary" },
    { key: "failed", count: documents.failed, variant: "destructive" },
  ];
}
