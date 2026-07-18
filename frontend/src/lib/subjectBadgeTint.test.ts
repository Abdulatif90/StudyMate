import { describe, expect, it } from "vitest";
import { subjectBadgeTint } from "./subjectBadgeTint";

describe("subjectBadgeTint", () => {
  it("is stable for the same seed", () => {
    expect(subjectBadgeTint("subject-abc")).toBe(subjectBadgeTint("subject-abc"));
  });

  it("spreads different seeds across more than one tint", () => {
    const tints = new Set(
      ["a", "b", "c", "d", "e", "f", "g", "h"].map((seed) => subjectBadgeTint(seed)),
    );
    expect(tints.size).toBeGreaterThan(1);
  });

  it("handles an empty seed without throwing", () => {
    expect(() => subjectBadgeTint("")).not.toThrow();
  });
});
