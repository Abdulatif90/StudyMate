import { cn } from "@/lib/utils";

/**
 * A shimmering placeholder block for loading state, sized/shaped by the caller via
 * `className` (e.g. `h-4 w-32` for a text line, `h-24 w-full` for a card body).
 *
 * Purely decorative (`aria-hidden`) — it carries no semantic "loading" announcement
 * itself. The caller's loading container should announce that separately (e.g.
 * `<div role="status" aria-label="Loading…">`), same as any other pending-state region.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
