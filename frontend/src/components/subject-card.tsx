import { BookOpen, ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { subjectBadgeTint } from "@/lib/subjectBadgeTint";
import { cn } from "@/lib/utils";

interface SubjectCardProps {
  href: string;
  name: string;
  /** The meta line (e.g. "3 documents · 2 due · 1 quiz") — already-formatted/
   * translated by the caller, same reasoning as `EmptyState`/`ErrorState`. */
  meta: ReactNode;
  /** Optional badge shown next to the title (e.g. "Shared" for an org subject). */
  badge?: ReactNode;
  /** An optional trailing action (e.g. a delete button) — rendered as a SIBLING of
   * the `<Link>`, never nested inside it, so clicking it can't also navigate (the
   * same nesting hazard fixed for the plain subjects list in an earlier increment).
   * When given, this replaces the chevron affordance (the action itself signals
   * there's something to do with this row); when omitted, the whole card — chevron
   * included — is one clickable link, matching the read-only dashboard preview use.
   */
  action?: ReactNode;
}

/**
 * The design prompt's subject card: icon badge + title + meta line, chevron-right
 * affordance, whole card clickable (the wrapping `<Link>`) with a hover lift + border
 * tint toward the brand color — the last part comes for free from `Card`'s existing
 * `interactive` variant (`hover:ring-primary/40`, and `--primary` IS the brand teal),
 * no separate treatment needed here.
 */
export function SubjectCard({ href, name, meta, badge, action }: SubjectCardProps) {
  return (
    <Card interactive className="h-full">
      <CardContent className="flex items-center gap-3 py-3">
        <Link href={href} className="flex min-w-0 flex-1 items-center gap-3">
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-[9px]",
              subjectBadgeTint(href),
            )}
          >
            <BookOpen className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <p className="truncate text-sm font-medium">{name}</p>
              {badge}
            </div>
            <p className="truncate text-xs text-muted-foreground">{meta}</p>
          </div>
          {!action && (
            <ChevronRight
              aria-hidden
              className="size-4 shrink-0 text-muted-foreground transition-transform group-hover/card:translate-x-0.5"
            />
          )}
        </Link>
        {action}
      </CardContent>
    </Card>
  );
}
