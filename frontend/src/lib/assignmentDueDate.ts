export type DueStatus = "none" | "upcoming" | "overdue";

/**
 * Classifies an assignment's `due_at` relative to `now`, for a simple due-date badge.
 * Purely presentational — the backend has no deadline enforcement of its own (a due date
 * is informational, never blocks a late submission), so this never needs to match any
 * server-side rule, just be a sensible default (`now` is a param so it's testable without
 * mocking the clock).
 */
export function dueStatus(dueAt: string | null | undefined, now: Date = new Date()): DueStatus {
  if (!dueAt) return "none";
  return new Date(dueAt).getTime() < now.getTime() ? "overdue" : "upcoming";
}
