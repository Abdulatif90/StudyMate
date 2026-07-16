import { describe, expect, it } from "vitest";
import { filterConversationsBySubject } from "./conversationFilter";

const SUBJECT_A = "11111111-1111-1111-1111-111111111111";
const SUBJECT_B = "22222222-2222-2222-2222-222222222222";

describe("filterConversationsBySubject", () => {
  it("keeps only conversations matching the given subject_id", () => {
    const conversations = [
      { id: "c1", subject_id: SUBJECT_A, title: null, created_at: "2026-01-01T00:00:00Z" },
      { id: "c2", subject_id: SUBJECT_B, title: null, created_at: "2026-01-02T00:00:00Z" },
      { id: "c3", subject_id: SUBJECT_A, title: "Chat", created_at: "2026-01-03T00:00:00Z" },
    ];

    const result = filterConversationsBySubject(conversations, SUBJECT_A);

    expect(result.map((c) => c.id)).toEqual(["c1", "c3"]);
  });

  it("returns an empty array when nothing matches", () => {
    const conversations = [
      { id: "c1", subject_id: SUBJECT_B, title: null, created_at: "2026-01-01T00:00:00Z" },
    ];

    expect(filterConversationsBySubject(conversations, SUBJECT_A)).toEqual([]);
  });
});
