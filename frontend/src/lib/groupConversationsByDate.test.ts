import { describe, expect, it } from "vitest";
import { groupConversationsByDate } from "./groupConversationsByDate";

// Built with the LOCAL constructor (not a fixed "...Z" instant) so NOW always
// lines up with the impl's local-calendar-day bucketing, regardless of which
// timezone the test runner is in.
const NOW = new Date(2026, 6, 16, 12, 0, 0);

/**
 * Builds an ISO timestamp for a conversation created exactly `n` local
 * calendar days before NOW's calendar day, at local noon (comfortably clear
 * of any midnight boundary, in any timezone). This is a straight, honest
 * "n days ago" — no off-by-one shifting baked in.
 */
function fixtureDaysAgo(n: number): string {
  const d = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() - n, 12, 0, 0);
  return d.toISOString();
}

function conversation(id: string, createdAt: string) {
  return { id, subject_id: "s1", title: null, created_at: createdAt };
}

describe("groupConversationsByDate", () => {
  it("buckets conversations into Today/Yesterday/Previous 7/Previous 30/Older", () => {
    const conversations = [
      conversation("today", fixtureDaysAgo(0)),
      conversation("yesterday", fixtureDaysAgo(1)),
      conversation("this-week", fixtureDaysAgo(3)),
      conversation("this-month", fixtureDaysAgo(15)),
      conversation("old", fixtureDaysAgo(200)),
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
    expect(groups[1].conversations.map((c) => c.id)).toEqual(["yesterday"]);
    expect(groups[2].conversations.map((c) => c.id)).toEqual(["this-week"]);
    expect(groups[3].conversations.map((c) => c.id)).toEqual(["this-month"]);
    expect(groups[4].conversations.map((c) => c.id)).toEqual(["old"]);
  });

  it("buckets a conversation created yesterday evening as Yesterday, not Today (regression)", () => {
    // This is the exact off-by-one the impl used to get wrong: comparing
    // today's local midnight to the raw created_at timestamp instead of to
    // created_at's own local day-start shifted every bucket by one day, so
    // "yesterday evening" would incorrectly fall inside "Today".
    const yesterdayEvening = new Date(
      NOW.getFullYear(),
      NOW.getMonth(),
      NOW.getDate() - 1,
      20,
      0,
      0
    ).toISOString();

    const groups = groupConversationsByDate(
      [conversation("yesterday-evening", yesterdayEvening)],
      NOW
    );

    expect(groups).toEqual([
      { label: "Yesterday", conversations: [expect.objectContaining({ id: "yesterday-evening" })] },
    ]);
  });

  it("omits groups with no conversations", () => {
    const groups = groupConversationsByDate(
      [conversation("today", fixtureDaysAgo(0))],
      NOW
    );
    expect(groups).toEqual([{ label: "Today", conversations: [expect.objectContaining({ id: "today" })] }]);
  });

  it("returns an empty array for no conversations", () => {
    expect(groupConversationsByDate([], NOW)).toEqual([]);
  });
});
