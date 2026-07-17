import { describe, expect, it } from "vitest";
import { GRADE_BUTTONS, isLapseGrade } from "./gradeButtons";

describe("GRADE_BUTTONS", () => {
  it("has exactly four labeled buttons", () => {
    expect(GRADE_BUTTONS.map((b) => b.label)).toEqual(["Again", "Hard", "Good", "Easy"]);
  });

  it("maps every button to an integer within SM-2's 0-5 range", () => {
    for (const button of GRADE_BUTTONS) {
      expect(Number.isInteger(button.grade)).toBe(true);
      expect(button.grade).toBeGreaterThanOrEqual(0);
      expect(button.grade).toBeLessThanOrEqual(5);
    }
  });

  it("pins the exact Anki-style grade for each button", () => {
    const byLabel = Object.fromEntries(GRADE_BUTTONS.map((b) => [b.label, b.grade]));
    expect(byLabel).toEqual({ Again: 1, Hard: 3, Good: 4, Easy: 5 });
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
    const results = GRADE_BUTTONS.map((b) => [b.label, isLapseGrade(b.grade)]);
    expect(results).toEqual([
      ["Again", true],
      ["Hard", false],
      ["Good", false],
      ["Easy", false],
    ]);
  });
});
