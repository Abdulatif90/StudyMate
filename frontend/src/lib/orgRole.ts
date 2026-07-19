/**
 * Client mirror of the backend's Clerk org role -> capability mapping
 * (`backend/app/core/org.py`). Kept in sync deliberately: the UI decides what to
 * show a teacher vs a student from the SAME role keys the API authorizes on, so the
 * two must not drift.
 *
 * Clerk's default org roles are admin and member. CONFIRMED AT RUNTIME (via
 * `GET /org` in a real signed-in session with an active org) that the role arrives
 * as the BARE slug (`"admin"`), NOT the `org:`-prefixed form (`"org:admin"`) the
 * SDK docs suggest — which form an instance emits depends on its session-token
 * version, so both are normalized and accepted here, mirroring `org.py`. We map
 * the admin-tier role to the "teacher" capability and everything else (member,
 * unknown custom role, or no active org) to "student" — student is the safe
 * default since teacher is the privileged capability. A custom `teacher`/
 * `org:teacher` role is honored too, in case the instance adds one later.
 */

export type OrgCapability = "teacher" | "student";

const TEACHER_ROLE_KEYS = new Set(["admin", "teacher"]);

/**
 * Strip an optional `org:`-style prefix and lowercase a Clerk role slug, so
 * comparisons accept both the bare (`"admin"`, confirmed at runtime) and
 * `org:`-prefixed (`"org:admin"`) forms uniformly.
 */
function normalizeRole(role: string | null | undefined): string | null {
  if (role == null) return null;
  const parts = role.split(":");
  return parts[parts.length - 1].toLowerCase();
}

/** Whether a Clerk org role key grants the teacher/admin capability. */
export function isTeacherRole(role: string | null | undefined): boolean {
  const normalized = normalizeRole(role);
  return normalized != null && TEACHER_ROLE_KEYS.has(normalized);
}

/** Map a Clerk org role key to our capability: "teacher" or "student". */
export function orgCapability(role: string | null | undefined): OrgCapability {
  return isTeacherRole(role) ? "teacher" : "student";
}
