import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  message: string;
  retryLabel?: string;
  onRetry?: () => void;
}

/**
 * Shared "couldn't load this" placeholder — icon + message + an optional Retry action,
 * replacing the plain `<p className="text-destructive">` pattern used across mutations
 * before this increment (FRONTEND.md §3.2 reserves inline destructive text for
 * persistent in-context state, not a one-shot load failure). `retryLabel` has no
 * default so every caller passes an already-translated string, same reasoning as
 * `EmptyState` — this component has no copy of its own to translate.
 */
export function ErrorState({ message, retryLabel, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
      <AlertTriangle aria-hidden className="size-6 text-destructive" />
      <p className="text-sm text-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-1" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
