/**
 * Client-side mirror of the backend's assignment create/delete gates
 * (`backend/app/modules/assignments/service.py` + the `require_teacher` dependency on
 * `POST /assignments`). UX only — the backend still enforces both (403/404 on a doomed
 * request); this just decides what the UI offers so a caller isn't led into a request
 * that's certain to fail.
 */

import type { OrgCapability } from "@/lib/orgRole";

/** Only a teacher/admin of the active org may create an assignment (mirrors the
 * `require_teacher` dependency guarding `POST /assignments`). */
export function canCreateAssignment(capability: OrgCapability): boolean {
  return capability === "teacher";
}

/**
 * An assignment may be deleted by its creator OR any teacher/admin of its org — mirrors
 * `service.delete_assignment`'s gate exactly (`owner_id == caller_id or
 * is_teacher_role(org_role)`). A plain member who didn't create it may not.
 */
export function canDeleteAssignment(
  callerId: string | null | undefined,
  ownerId: string,
  capability: OrgCapability,
): boolean {
  return capability === "teacher" || callerId === ownerId;
}
