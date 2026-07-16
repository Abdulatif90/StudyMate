import type { components } from "@/lib/api/schema";

type DocumentRead = components["schemas"]["DocumentRead"];

export const DOCUMENTS_POLL_INTERVAL_MS = 2000;

/**
 * How often to refetch the documents list. Processing is async now (an Inngest job
 * parses/chunks/embeds after upload), so a freshly uploaded document sits on
 * `pending` until the job resolves it — poll while any document is still pending so
 * its badge flips to ready/failed on its own, and stop once none are (no point
 * polling a settled list). Returns `false` (TanStack Query's "don't poll") when the
 * data is absent or nothing is pending.
 */
export function documentsRefetchInterval(
  documents: DocumentRead[] | undefined
): number | false {
  if (!documents) return false;
  return documents.some((document) => document.status === "pending")
    ? DOCUMENTS_POLL_INTERVAL_MS
    : false;
}
