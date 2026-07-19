import { describe, expect, it } from "vitest";
import { canShowTeamUpgrade } from "./teamUpgrade";

describe("canShowTeamUpgrade", () => {
  it("shows for a teacher/admin with an active org (prefixed and bare role)", () => {
    expect(canShowTeamUpgrade(true, "org:admin")).toBe(true);
    expect(canShowTeamUpgrade(true, "admin")).toBe(true);
    expect(canShowTeamUpgrade(true, "org:teacher")).toBe(true);
  });

  it("hides for a plain member even with an active org", () => {
    expect(canShowTeamUpgrade(true, "org:member")).toBe(false);
    expect(canShowTeamUpgrade(true, "member")).toBe(false);
  });

  it("hides for a teacher/admin role with no active org", () => {
    expect(canShowTeamUpgrade(false, "org:admin")).toBe(false);
    expect(canShowTeamUpgrade(false, "admin")).toBe(false);
  });

  it("hides for unknown/empty roles regardless of org", () => {
    expect(canShowTeamUpgrade(true, "")).toBe(false);
    expect(canShowTeamUpgrade(true, null)).toBe(false);
    expect(canShowTeamUpgrade(true, undefined)).toBe(false);
    expect(canShowTeamUpgrade(false, null)).toBe(false);
  });
});
