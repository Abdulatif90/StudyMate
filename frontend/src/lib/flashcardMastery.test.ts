import { describe, expect, it } from "vitest";
import { masteryRows, percentMature } from "./flashcardMastery";

function flashcards(overrides: Partial<Record<string, number>> = {}) {
  return {
    total: 10,
    due: 0,
    new: 4,
    learning: 3,
    mature: 3,
    ...overrides,
  };
}

describe("masteryRows", () => {
  it("returns new/learning/mature in that order with labels and status words", () => {
    const rows = masteryRows(flashcards());
    expect(rows.map((r) => r.key)).toEqual(["new", "learning", "mature"]);
    expect(rows.map((r) => r.label)).toEqual(["New", "Learning", "Mature"]);
    expect(rows.every((r) => r.status.length > 0)).toBe(true); // never color-alone
  });

  it("computes counts straight from the backend's buckets, no re-bucketing", () => {
    const rows = masteryRows(flashcards({ new: 4, learning: 3, mature: 3 }));
    expect(rows.find((r) => r.key === "new")?.count).toBe(4);
    expect(rows.find((r) => r.key === "learning")?.count).toBe(3);
    expect(rows.find((r) => r.key === "mature")?.count).toBe(3);
  });

  it("computes percent of total for each bucket", () => {
    const rows = masteryRows(flashcards({ total: 10, new: 4, learning: 3, mature: 3 }));
    expect(rows.map((r) => r.percent)).toEqual([40, 30, 30]);
  });

  it("returns all-zero percentages for an empty deck instead of NaN", () => {
    const rows = masteryRows(flashcards({ total: 0, new: 0, learning: 0, mature: 0 }));
    expect(rows.every((r) => r.percent === 0)).toBe(true);
    expect(rows.every((r) => Number.isFinite(r.percent))).toBe(true);
  });
});

describe("percentMature", () => {
  it("computes the percent of the deck that's mature", () => {
    expect(percentMature(flashcards({ total: 20, mature: 5 }))).toBe(25);
  });

  it("returns 0 for an empty deck, not NaN", () => {
    expect(percentMature(flashcards({ total: 0, mature: 0 }))).toBe(0);
  });

  it("returns 100 when every card is mature", () => {
    expect(percentMature(flashcards({ total: 5, mature: 5 }))).toBe(100);
  });
});
