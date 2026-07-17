import Link from "next/link";
import { Button } from "@/components/ui/button";

/** Inline "you've hit a plan limit → upgrade" callout, shown on the 402 path (e.g. when a
 * create is rejected). The message comes from the backend's 402 body via
 * `parsePlanLimitError`, so it already names the limit and cap; this just pairs it with a
 * route to the billing page. Paired icon-free but colour + an explicit "Upgrade" label,
 * never colour alone (FRONTEND.md §2.5). */
export function UpgradePrompt({ message }: { message: string }) {
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-foreground">{message}</p>
      <Button
        size="sm"
        nativeButton={false}
        render={<Link href="/billing">Upgrade</Link>}
        className="shrink-0"
      />
    </div>
  );
}
