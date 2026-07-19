/**
 * Client mirror of the backend's Clerk org role -> capability mapping
 * (`backend/app/core/org.py`). Kept in sync deliberately: the UI decides what to
 * show a teacher vs a student from the SAME role keys the API authorizes on, so the
 * two must not drift.
 *
 * Clerk's default org roles are `org:admin` and `org:member`. We map the admin-tier
 * role to the "teacher" capability and everything else (member, unknown custom role,
 * or no active org) to "student" — student is the safe default since teacher is the
 * privileged capability. A custom `org:teacher` role is honored too, in case the
 * instance adds one later.
 */

export type OrgCapability = "teacher" | "student";

const TEACHER_ROLE_KEYS = new Set(["org:admin", "org:teacher"]);

/** Whether a Clerk org role key grants the teacher/admin capability. */
export function isTeacherRole(role: string | null | undefined): boolean {
  return role != null && TEACHER_ROLE_KEYS.has(role);
}

/** Map a Clerk org role key to our capability: "teacher" or "student". */
export function orgCapability(role: string | null | undefined): OrgCapability {
  return isTeacherRole(role) ? "teacher" : "student";
}
