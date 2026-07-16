import type { components } from "@/lib/api/schema";

type ConversationRead = components["schemas"]["ConversationRead"];

/** GET /conversations is owner-scoped across all subjects — keep only this subject's. */
export function filterConversationsBySubject(
  conversations: ConversationRead[],
  subjectId: string
): ConversationRead[] {
  return conversations.filter((conversation) => conversation.subject_id === subjectId);
}
