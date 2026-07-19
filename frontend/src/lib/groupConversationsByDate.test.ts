import { describe, expect, it } from "vitest";
import { groupConversationsByDate } from "./groupConversationsByDate";

// Built with the LOCAL constructor (not a fixed "...Z" instant) so NOW always
// lines up with the impl's local-calendar-day bucketing, regardless of which
// timezone the test runner is in.
const NOW = new Date(2026, 6, 16, 12, 0, 0);

/**
 * Builds an ISO timestamp that the impl will bucket at exactly `daysAgo`.
 *
 * The impl computes `daysAgo = floor((startOfToday - createdAt) / DAY)`,
 * where `startOfToday` is local midnight of NOW's calendar day. To land
 * exactly on a given `daysAgo`, the timestamp needs to sit at local noon on
 * the calendar day that is `daysAgo + 1` days before NOW's calendar day —
 * noon keeps it comfortably clear of any midnight boundary, in any timezone.
 */
function fixtureAtDaysAgo(daysAgo: number): string {
  const d = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() - (daysAgo + 1), 12, 0, 0);
  return d.toISOString();
}

function conversation(id: string, createdAt: string) {
  return { id, subject_id: "s1", title: null, created_at: createdAt };
}

describe("groupConversationsByDate", () => {
  it("buckets conversations into Today/Yesterday/Previous 7/Previous 30/Older", () => {
    const conversations = [
      conversation("today", fixtureAtDaysAgo(0)),
      conversation("yesterday", fixtureAtDaysAgo(1)),
      conversation("this-week", fixtureAtDaysAgo(4)),
      conversation("this-month", fixtureAtDaysAgo(20)),
      conversation("old", fixtureAtDaysAgo(200)),
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
      [conversation("today", fixtureAtDaysAgo(0))],
      NOW
    );
    expect(groups).toEqual([{ label: "Today", conversations: [expect.objectContaining({ id: "today" })] }]);
  });

  it("returns an empty array for no conversations", () => {
    expect(groupConversationsByDate([], NOW)).toEqual([]);
  });
});
