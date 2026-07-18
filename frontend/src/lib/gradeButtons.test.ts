import { describe, expect, it } from "vitest";
import { GRADE_BUTTONS, isLapseGrade } from "./gradeButtons";

describe("GRADE_BUTTONS", () => {
  it("has exactly four keyed buttons", () => {
    expect(GRADE_BUTTONS.map((b) => b.key)).toEqual(["again", "hard", "good", "easy"]);
  });

  it("maps every button to an integer within SM-2's 0-5 range", () => {
    for (const button of GRADE_BUTTONS) {
      expect(Number.isInteger(button.grade)).toBe(true);
      expect(button.grade).toBeGreaterThanOrEqual(0);
      expect(button.grade).toBeLessThanOrEqual(5);
    }
  });

  it("pins the exact Anki-style grade for each button", () => {
    const byKey = Object.fromEntries(GRADE_BUTTONS.map((b) => [b.key, b.grade]));
    expect(byKey).toEqual({ again: 1, hard: 3, good: 4, easy: 5 });
  });
});

describe("isLapseGrade", () => {
  it("treats grades below the passing threshold as a lapse", () => {
    expect(isLapseGrade(0)).toBe(true);
    expect(isLapseGrade(1)).toBe(true);
    expect(isLapseGrade(2)).toBe(true);
  });

  it("treats grades at or above the passing threshold as a pass", () => {
    expect(isLapseGrade(3)).toBe(false);
    expect(isLapseGrade(4)).toBe(false);
    expect(isLapseGrade(5)).toBe(false);
  });

  it("only the Again button is a lapse; Hard/Good/Easy all pass", () => {
    const results = GRADE_BUTTONS.map((b) => [b.key, isLapseGrade(b.grade)]);
    expect(results).toEqual([
      ["again", true],
      ["hard", false],
      ["good", false],
      ["easy", false],
    ]);
  });
});
