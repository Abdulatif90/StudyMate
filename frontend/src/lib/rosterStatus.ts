/**
 * Classifies a failed roster fetch's HTTP status into a display bucket. The backend
 * (`GET /assignments/{id}/roster`) returns 503 when Clerk isn't configured on the server
 * (a standing capability gap, not a transient failure) and 502 on an upstream Clerk
 * failure — both get a quiet inline note per FRONTEND.md's toast-vs-inline rule, rather
 * than an error toast or a crash; the submissions list above still renders either way.
 */

export type RosterErrorKind = "unavailable" | "gateway" | "other";

export function classifyRosterError(status: number | undefined): RosterErrorKind {
  if (status === 503) return "unavailable";
  if (status === 502) return "gateway";
  return "other";
}
