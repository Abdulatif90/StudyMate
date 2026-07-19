/**
 * Resolves a roster entry's opaque Clerk `user_id` to a display name, using the org's
 * membership list the teacher's page already loads via `useOrganization({ memberships })`.
 * Kept structurally typed (not importing Clerk's SDK type directly) so this stays a plain,
 * dependency-free unit — matching this codebase's existing pattern of minimal local
 * interfaces for helpers that touch third-party shapes (see `assignmentQuizStatus`'s
 * `MinimalSubmission`).
 *
 * Falls back to a shortened id when the member isn't found (e.g. Clerk membership list
 * hasn't loaded yet, or — per `AssignmentRoster`'s contract — an ex-member who submitted
 * then left the org) rather than blocking the roster UI on a full name.
 */

export interface RosterMembershipLike {
  publicUserData?: {
    userId?: string | null;
    identifier?: string | null;
    firstName?: string | null;
    lastName?: string | null;
  } | null;
}

const SHORT_ID_LENGTH = 8;

export function resolveMemberName(
  userId: string,
  memberships: RosterMembershipLike[] | null | undefined,
): string {
  const match = memberships?.find((m) => m.publicUserData?.userId === userId);
  const data = match?.publicUserData;
  if (data) {
    const fullName = [data.firstName, data.lastName]
      .filter((part): part is string => !!part && part.trim().length > 0)
      .join(" ");
    if (fullName) return fullName;
    if (data.identifier) return data.identifier;
  }
  return `${userId.slice(0, SHORT_ID_LENGTH)}…`;
}
