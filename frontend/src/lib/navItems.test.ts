import { describe, expect, it } from "vitest";
import { isNavItemActive, NAV_ITEMS } from "./navItems";

describe("NAV_ITEMS", () => {
  it("covers dashboard, subjects, team, assignments, billing, and support", () => {
    expect(NAV_ITEMS.map((item) => item.href)).toEqual([
      "/dashboard",
      "/subjects",
      "/team",
      "/assignments",
      "/billing",
      "/support",
    ]);
  });
});

describe("isNavItemActive", () => {
  it("matches an exact pathname", () => {
    expect(isNavItemActive("/subjects", "/subjects")).toBe(true);
  });

  it("matches a sub-route of the destination", () => {
    expect(isNavItemActive("/subjects/abc123/quizzes", "/subjects")).toBe(true);
  });

  it("does not match an unrelated route sharing only a text prefix", () => {
    expect(isNavItemActive("/subjects-archive", "/subjects")).toBe(false);
  });

  it("does not match a sibling destination", () => {
    expect(isNavItemActive("/billing", "/subjects")).toBe(false);
    expect(isNavItemActive("/dashboard", "/subjects")).toBe(false);
  });

  it("does not match the root path for any destination", () => {
    expect(isNavItemActive("/", "/dashboard")).toBe(false);
  });
});
