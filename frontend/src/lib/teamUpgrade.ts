import { isTeacherRole } from "@/lib/orgRole";

/**
 * UX-only gate for the billing page's "Team Plan" upgrade card: only a teacher/admin
 * WITH an active organization should see it (a plain member, or anyone with no active
 * org, shouldn't). Mirrors the backend's real guard on `POST /billing/team-checkout`
 * (`require_teacher`, `app/core/auth.py`) — that dependency is the actual enforcement;
 * this just decides what the UI offers so a caller isn't led into a request that's
 * certain to 403.
 */
export function canShowTeamUpgrade(hasActiveOrg: boolean, role: string | null | undefined): boolean {
  return hasActiveOrg && isTeacherRole(role);
}
