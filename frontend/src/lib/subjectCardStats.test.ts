import { describe, expect, it } from "vitest";
import { subjectCardStats } from "./subjectCardStats";

function progress(overrides: Partial<Parameters<typeof subjectCardStats>[0]> = {}) {
  return {
    subject_id: "s1",
    documents: { total: 0, ready: 0, pending: 0, failed: 0 },
    flashcards: { total: 0, due: 0, new: 0, learning: 0, mature: 0 },
    quiz_count: 0,
    ...overrides,
  };
}

describe("subjectCardStats", () => {
  it("returns zeroed stats for a subject with no material", () => {
    expect(subjectCardStats(progress())).toEqual([
      { key: "documents", value: 0 },
      { key: "flashcardsDue", value: 0 },
      { key: "quizzes", value: 0 },
    ]);
  });

  it("reports total documents, due flashcards (not the full deck), and quiz count", () => {
    const stats = subjectCardStats(
      progress({
        documents: { total: 5, ready: 3, pending: 1, failed: 1 },
        flashcards: { total: 20, due: 4, new: 10, learning: 4, mature: 6 },
        quiz_count: 2,
      })
    );
    expect(stats).toEqual([
      { key: "documents", value: 5 },
      { key: "flashcardsDue", value: 4 },
      { key: "quizzes", value: 2 },
    ]);
  });
});
