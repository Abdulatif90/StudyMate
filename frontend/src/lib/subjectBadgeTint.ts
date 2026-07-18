// A small, deterministic set of tinted badge colors, cycled by a stable hash of the
// subject's own id — "tinted background per subject/category" from the design prompt,
// without a real category field on Subject: the same subject always lands on the same
// tint (derived from its id, not randomized per render), and different subjects spread
// across the set rather than all sharing one color.
const BADGE_TINTS = [
  "bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300",
  "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
] as const;

/** A stable index into `BADGE_TINTS` for the given seed (a subject's id). Every term
 * added into `hash` is non-negative and the running total is kept `% length` at each
 * step, so the result is always a valid, non-negative index — no normalization needed
 * at the end. */
export function subjectBadgeTint(seed: string): string {
  let hash = 0;
  for (const char of seed) {
    hash = (hash * 31 + char.charCodeAt(0)) % BADGE_TINTS.length;
  }
  return BADGE_TINTS[hash];
}
