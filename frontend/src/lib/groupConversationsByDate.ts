import type { components } from "@/lib/api/schema";

type ConversationRead = components["schemas"]["ConversationRead"];

export interface ConversationGroup {
  label: string;
  conversations: ConversationRead[];
}

const DAY = 24 * 60 * 60 * 1000;
const GROUP_LABELS = ["Today", "Yesterday", "Previous 7 Days", "Previous 30 Days", "Older"] as const;

/** Buckets conversations the way Claude's/ChatGPT's sidebar does, so individual
 * items don't need their own per-conversation timestamp. */
export function groupConversationsByDate(
  conversations: ConversationRead[],
  now: Date = new Date()
): ConversationGroup[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();

  const buckets: Record<(typeof GROUP_LABELS)[number], ConversationRead[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    "Previous 30 Days": [],
    Older: [],
  };

  for (const conversation of conversations) {
    const daysAgo = Math.floor(
      (startOfToday - new Date(conversation.created_at).getTime()) / DAY
    );

    if (daysAgo <= 0) buckets.Today.push(conversation);
    else if (daysAgo === 1) buckets.Yesterday.push(conversation);
    else if (daysAgo <= 7) buckets["Previous 7 Days"].push(conversation);
    else if (daysAgo <= 30) buckets["Previous 30 Days"].push(conversation);
    else buckets.Older.push(conversation);
  }

  return GROUP_LABELS.filter((label) => buckets[label].length > 0).map((label) => ({
    label,
    conversations: buckets[label],
  }));
}
