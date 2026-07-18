import { describe, expect, it } from "vitest";
import { usageSeverity } from "./usageSeverity";
import type { UsageMeter } from "./planLimits";

function meter(overrides: Partial<UsageMeter> = {}): UsageMeter {
  return {
    key: "subjects",
    label: "Subjects",
    used: 0,
    cap: 3,
    unlimited: false,
    percent: 0,
    atLimit: false,
    ...overrides,
  };
}

describe("usageSeverity", () => {
  it("is null for an unlimited meter", () => {
    expect(usageSeverity(meter({ cap: null, unlimited: true, atLimit: false }))).toBeNull();
  });

  it("is normal well under the warning threshold", () => {
    expect(usageSeverity(meter({ used: 1, percent: 33 }))).toBe("normal");
  });

  it("turns warning at the threshold, before the cap is actually hit", () => {
    expect(usageSeverity(meter({ used: 2, cap: 3, percent: 67 }))).toBe("normal");
    expect(usageSeverity(meter({ used: 4, cap: 5, percent: 80, atLimit: false }))).toBe("warning");
  });

  it("is atLimit once the cap is fully consumed", () => {
    expect(usageSeverity(meter({ used: 3, cap: 3, percent: 100, atLimit: true }))).toBe(
      "atLimit"
    );
  });

  it("prefers atLimit over the percent-based warning check even if percent is stale", () => {
    // atLimit (used >= cap) is checked first and wins regardless of percent's own
    // rounding — this pins that ordering, not just the common case where both agree.
    expect(usageSeverity(meter({ used: 3, cap: 3, percent: 67, atLimit: true }))).toBe("atLimit");
  });
});
