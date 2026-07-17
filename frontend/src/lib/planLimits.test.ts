import { describe, expect, it } from "vitest";
import { meterPercent, usageMeters } from "./planLimits";
import type { components } from "@/lib/api/schema";

type PlanRead = components["schemas"]["PlanRead"];

function planRead(overrides: Partial<PlanRead> = {}): PlanRead {
  return {
    plan: "free",
    limits: {
      max_subjects: 3,
      max_documents_per_subject: 10,
      max_generations_per_day: 20,
    },
    usage: { subjects: 1, generations_today: 5 },
    ...overrides,
  };
}

describe("meterPercent", () => {
  it("computes a rounded percentage of the cap", () => {
    expect(meterPercent(3, 4)).toBe(75);
    expect(meterPercent(2, 3)).toBe(67); // 66.6… rounds to 67
  });

  it("is 0 at no usage and 100 when full", () => {
    expect(meterPercent(0, 20)).toBe(0);
    expect(meterPercent(20, 20)).toBe(100);
  });

  it("clamps over-cap usage to 100 instead of overflowing", () => {
    expect(meterPercent(25, 20)).toBe(100);
  });

  it("returns 0 for an unlimited (null) or non-positive cap, never NaN/Infinity", () => {
    expect(meterPercent(5, null)).toBe(0);
    expect(meterPercent(5, 0)).toBe(0);
    expect(Number.isFinite(meterPercent(5, null))).toBe(true);
  });
});

describe("usageMeters", () => {
  it("returns subjects + generations meters, in that order", () => {
    const meters = usageMeters(planRead());
    expect(meters.map((m) => m.key)).toEqual(["subjects", "generations"]);
  });

  it("carries used/cap and a percent for a finite cap", () => {
    const meters = usageMeters(
      planRead({ usage: { subjects: 2, generations_today: 5 } }),
    );
    const subjects = meters.find((m) => m.key === "subjects")!;
    expect(subjects.used).toBe(2);
    expect(subjects.cap).toBe(3);
    expect(subjects.unlimited).toBe(false);
    expect(subjects.percent).toBe(67);
    expect(subjects.atLimit).toBe(false);
  });

  it("flags atLimit exactly at the cap (and above)", () => {
    const atCap = usageMeters(
      planRead({ usage: { subjects: 3, generations_today: 0 } }),
    ).find((m) => m.key === "subjects")!;
    expect(atCap.atLimit).toBe(true);
  });

  it("marks a null cap unlimited with percent 0 and never atLimit", () => {
    const meters = usageMeters(
      planRead({
        plan: "business",
        limits: {
          max_subjects: null,
          max_documents_per_subject: null,
          max_generations_per_day: null,
        },
        usage: { subjects: 99, generations_today: 99 },
      }),
    );
    for (const meter of meters) {
      expect(meter.unlimited).toBe(true);
      expect(meter.percent).toBe(0);
      expect(meter.atLimit).toBe(false);
    }
  });
});
