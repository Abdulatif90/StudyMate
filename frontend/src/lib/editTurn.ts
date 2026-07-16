import type { components } from "@/lib/api/schema";

type Turn = components["schemas"]["ConversationTurnRead"];

/**
 * Splits a transcript at the turn being edited: everything from that turn
 * onward is "removed" (dropped from view while the edited question is
 * resent), everything before it is "remaining" (kept as-is). If `turnId`
 * isn't found, nothing is removed — the full list comes back as `remaining`.
 *
 * The caller is expected to hold on to `removed` and put it back if the
 * resend fails, rather than discarding it outright — otherwise a failed
 * edit/resend silently drops the question with no way to recover it.
 */
export function splitTurnsAtEdit(
  turns: Turn[],
  turnId: string
): { remaining: Turn[]; removed: Turn[] } {
  const editedIndex = turns.findIndex((turn) => turn.id === turnId);
  if (editedIndex === -1) return { remaining: turns, removed: [] };
  return { remaining: turns.slice(0, editedIndex), removed: turns.slice(editedIndex) };
}
