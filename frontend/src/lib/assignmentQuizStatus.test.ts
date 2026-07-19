import { describe, expect, it } from "vitest";
import { assignmentQuizStatus } from "./assignmentQuizStatus";

describe("assignmentQuizStatus", () => {
  it("is 'quiz-not-started' for a quiz-linked assignment with no submission", () => {
    expect(assignmentQuizStatus("quiz-1", null)).toEqual({ kind: "quiz-not-started" });
    expect(assignmentQuizStatus("quiz-1", undefined)).toEqual({ kind: "quiz-not-started" });
  });

  it("is 'quiz-completed' with the graded score once a submission exists", () => {
    expect(assignmentQuizStatus("quiz-1", { score: 4 })).toEqual({
      kind: "quiz-completed",
      score: 4,
    });
  });

  it("is 'quiz-completed' with a null score if the submission carries none", () => {
    expect(assignmentQuizStatus("quiz-1", { score: null })).toEqual({
      kind: "quiz-completed",
      score: null,
    });
    expect(assignmentQuizStatus("quiz-1", {})).toEqual({
      kind: "quiz-completed",
      score: null,
    });
  });

  it("is 'manual-not-done' for an assignment with no linked quiz and no submission", () => {
    expect(assignmentQuizStatus(null, null)).toEqual({ kind: "manual-not-done" });
    expect(assignmentQuizStatus(undefined, null)).toEqual({ kind: "manual-not-done" });
  });

  it("is 'manual-done' for an assignment with no linked quiz once submitted", () => {
    expect(assignmentQuizStatus(null, { score: null })).toEqual({ kind: "manual-done" });
  });
});
