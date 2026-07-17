import { describe, expect, it } from "vitest";
import { reviewProgress } from "./reviewProgress";

describe("reviewProgress", () => {
  it("reports the first card as 1 of N", () => {
    expect(reviewProgress(5, 0)).toEqual({
      current: 1,
      total: 5,
      remaining: 5,
      isComplete: false,
    });
  });

  it("reports a middle card correctly", () => {
    expect(reviewProgress(5, 2)).toEqual({
      current: 3,
      total: 5,
      remaining: 3,
      isComplete: false,
    });
  });

  it("reports the last card as not yet complete", () => {
    expect(reviewProgress(5, 4)).toEqual({
      current: 5,
      total: 5,
      remaining: 1,
      isComplete: false,
    });
  });

  it("is complete once the index reaches the total", () => {
    expect(reviewProgress(5, 5)).toEqual({
      current: 5,
      total: 5,
      remaining: 0,
      isComplete: true,
    });
  });

  it("is complete for an empty session", () => {
    expect(reviewProgress(0, 0)).toEqual({
      current: 0,
      total: 0,
      remaining: 0,
      isComplete: true,
    });
  });

  it("clamps an out-of-range index instead of going negative", () => {
    expect(reviewProgress(3, 10).remaining).toBe(0);
    expect(reviewProgress(3, 10).isComplete).toBe(true);
  });
});
