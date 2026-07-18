import { describe, expect, it } from "vitest";
import { onboardingSteps } from "./onboardingChecklist";

function progress(overrides: Partial<Parameters<typeof onboardingSteps>[0]> = {}) {
  return {
    subject_count: 0,
    documents: { total: 0, ready: 0, pending: 0, failed: 0 },
    flashcards: { total: 0, due: 0, new: 0, learning: 0, mature: 0 },
    quiz_count: 0,
    ...overrides,
  };
}

describe("onboardingSteps", () => {
  it("marks every step undone for a brand-new account", () => {
    expect(onboardingSteps(progress())).toEqual([
      { key: "createSubject", done: false },
      { key: "uploadDocument", done: false },
      { key: "tryGeneration", done: false },
    ]);
  });

  it("marks createSubject done once a subject exists, others still pending", () => {
    const steps = onboardingSteps(progress({ subject_count: 1 }));
    expect(steps).toEqual([
      { key: "createSubject", done: true },
      { key: "uploadDocument", done: false },
      { key: "tryGeneration", done: false },
    ]);
  });

  it("marks uploadDocument done once any document exists", () => {
    const steps = onboardingSteps(
      progress({ subject_count: 1, documents: { total: 1, ready: 0, pending: 1, failed: 0 } })
    );
    expect(steps.find((s) => s.key === "uploadDocument")?.done).toBe(true);
  });

  it("marks tryGeneration done from a quiz alone", () => {
    const steps = onboardingSteps(progress({ quiz_count: 1 }));
    expect(steps.find((s) => s.key === "tryGeneration")?.done).toBe(true);
  });

  it("marks tryGeneration done from flashcards alone, with no quizzes", () => {
    const steps = onboardingSteps(
      progress({ flashcards: { total: 3, due: 3, new: 3, learning: 0, mature: 0 } })
    );
    expect(steps.find((s) => s.key === "tryGeneration")?.done).toBe(true);
  });

  it("marks every step done once all three are satisfied", () => {
    const steps = onboardingSteps(
      progress({
        subject_count: 2,
        documents: { total: 3, ready: 3, pending: 0, failed: 0 },
        quiz_count: 1,
      })
    );
    expect(steps.every((s) => s.done)).toBe(true);
  });
});
