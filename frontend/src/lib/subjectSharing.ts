/**
 * UX helpers for org-owned (read-shared) subjects — Phase 5 increment 2.
 *
 * These decide only what the UI SHOWS. The backend's `can_write_subject` (a 403/404) is
 * the real authorization guard; hiding a write action a member can't perform is just so
 * they don't hit an error they could have been spared. Kept in sync with the backend
 * rule and `orgRole.ts` (same role keys) so the two can't drift.
 */

import type { OrgCapability } from "@/lib/orgRole";

/** A subject read shape carrying its org ownership (null/absent = private). */
export interface ShareableSubject {
  org_id?: string | null;
}

/** Whether a subject is org-owned (read-shared with an org), vs personal/private. */
export function isOrgSubject(subject: ShareableSubject): boolean {
  return subject.org_id != null;
}

/**
 * Whether the current caller may perform WRITE actions (upload / delete / add) on a
 * subject shown in their subject list or detail view.
 *
 * The list/detail views only ever show a caller their OWN subjects plus their ACTIVE
 * org's subjects, so:
 * - a personal subject (`org_id == null`) is always the caller's own → writable;
 * - an org subject is writable only by a teacher/admin of that (active) org.
 *
 * This mirrors the backend `can_write_subject` for exactly those two cases; it is NOT a
 * general authorization function (it assumes the subject is one the caller can already
 * see), which is why it takes just the capability, not a full role/ownership check.
 */
export function canWriteSharedSubject(
  orgId: string | null | undefined,
  capability: OrgCapability,
): boolean {
  return orgId == null || capability === "teacher";
}
