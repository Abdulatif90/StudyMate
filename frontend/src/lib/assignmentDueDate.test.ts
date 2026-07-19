import { describe, expect, it } from "vitest";
import { dueStatus } from "./assignmentDueDate";

const NOW = new Date("2026-07-20T12:00:00.000Z");

describe("dueStatus", () => {
  it("returns 'none' when there is no due date", () => {
    expect(dueStatus(null, NOW)).toBe("none");
    expect(dueStatus(undefined, NOW)).toBe("none");
  });

  it("returns 'upcoming' for a future due date", () => {
    expect(dueStatus("2026-07-21T12:00:00.000Z", NOW)).toBe("upcoming");
  });

  it("returns 'overdue' for a past due date", () => {
    expect(dueStatus("2026-07-19T12:00:00.000Z", NOW)).toBe("overdue");
  });

  it("treats the exact current instant as not yet overdue", () => {
    expect(dueStatus(NOW.toISOString(), NOW)).toBe("upcoming");
  });
});
