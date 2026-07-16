import { describe, expect, it } from "vitest";
import { formatRelativeTime } from "./relativeTime";

const NOW = new Date("2026-07-16T12:00:00Z");

describe("formatRelativeTime", () => {
  it("returns 'just now' for timestamps under a minute old", () => {
    expect(formatRelativeTime("2026-07-16T11:59:30Z", NOW)).toBe("just now");
  });

  it("formats minutes for timestamps under an hour old", () => {
    expect(formatRelativeTime("2026-07-16T11:55:00Z", NOW)).toBe("5m ago");
  });

  it("formats hours for timestamps under a day old", () => {
    expect(formatRelativeTime("2026-07-16T09:00:00Z", NOW)).toBe("3h ago");
  });

  it("formats days for timestamps under a week old", () => {
    expect(formatRelativeTime("2026-07-13T12:00:00Z", NOW)).toBe("3d ago");
  });

  it("falls back to a date string for timestamps a week or older", () => {
    const result = formatRelativeTime("2026-06-01T12:00:00Z", NOW);
    expect(result).toBe(new Date("2026-06-01T12:00:00Z").toLocaleDateString());
  });
});
