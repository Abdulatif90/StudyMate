import { describe, expect, it } from "vitest";
import { documentStatusRows } from "./documentProgress";

describe("documentStatusRows", () => {
  it("returns ready/pending/failed in that order with counts", () => {
    const rows = documentStatusRows({ total: 6, ready: 3, pending: 2, failed: 1 });
    expect(rows.map((r) => r.key)).toEqual(["ready", "pending", "failed"]);
    expect(rows.map((r) => r.count)).toEqual([3, 2, 1]);
  });

  it("maps each status to the same badge variant used elsewhere in the app", () => {
    const rows = documentStatusRows({ total: 3, ready: 1, pending: 1, failed: 1 });
    expect(rows.find((r) => r.key === "ready")?.variant).toBe("default");
    expect(rows.find((r) => r.key === "pending")?.variant).toBe("secondary");
    expect(rows.find((r) => r.key === "failed")?.variant).toBe("destructive");
  });

  it("handles an all-zero count set", () => {
    const rows = documentStatusRows({ total: 0, ready: 0, pending: 0, failed: 0 });
    expect(rows.every((r) => r.count === 0)).toBe(true);
  });
});
