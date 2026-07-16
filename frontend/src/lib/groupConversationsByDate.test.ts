import { describe, expect, it } from "vitest";
import { groupConversationsByDate } from "./groupConversationsByDate";

const NOW = new Date("2026-07-16T15:00:00Z");

function conversation(id: string, createdAt: string) {
  return { id, subject_id: "s1", title: null, created_at: createdAt };
}

describe("groupConversationsByDate", () => {
  it("buckets conversations into Today/Yesterday/Previous 7/Previous 30/Older", () => {
    const conversations = [
      conversation("today", "2026-07-16T09:00:00Z"),
      conversation("yesterday", "2026-07-15T09:00:00Z"),
      conversation("this-week", "2026-07-12T09:00:00Z"),
      conversation("this-month", "2026-06-25T09:00:00Z"),
      conversation("old", "2026-01-01T09:00:00Z"),
    ];

    const groups = groupConversationsByDate(conversations, NOW);

    expect(groups.map((g) => g.label)).toEqual([
      "Today",
      "Yesterday",
      "Previous 7 Days",
      "Previous 30 Days",
      "Older",
    ]);
    expect(groups[0].conversations.map((c) => c.id)).toEqual(["today"]);
    expect(groups[4].conversations.map((c) => c.id)).toEqual(["old"]);
  });

  it("omits groups with no conversations", () => {
    const groups = groupConversationsByDate(
      [conversation("today", "2026-07-16T09:00:00Z")],
      NOW
    );
    expect(groups).toEqual([{ label: "Today", conversations: [expect.objectContaining({ id: "today" })] }]);
  });

  it("returns an empty array for no conversations", () => {
    expect(groupConversationsByDate([], NOW)).toEqual([]);
  });
});
