import { describe, expect, it } from "vitest";
import { isTeacherRole, orgCapability } from "./orgRole";

describe("orgRole", () => {
  it("treats the admin role as teacher (prefixed and bare)", () => {
    // CONFIRMED AT RUNTIME (via GET /org) that Clerk can emit either form —
    // both must map to the teacher capability.
    expect(isTeacherRole("org:admin")).toBe(true);
    expect(orgCapability("org:admin")).toBe("teacher");
    expect(isTeacherRole("admin")).toBe(true);
    expect(orgCapability("admin")).toBe("teacher");
  });

  it("honors a custom teacher role (prefixed and bare)", () => {
    expect(isTeacherRole("org:teacher")).toBe(true);
    expect(orgCapability("org:teacher")).toBe("teacher");
    expect(isTeacherRole("teacher")).toBe(true);
    expect(orgCapability("teacher")).toBe("teacher");
  });

  it("treats the member role as student (prefixed and bare)", () => {
    expect(isTeacherRole("org:member")).toBe(false);
    expect(orgCapability("org:member")).toBe("student");
    expect(isTeacherRole("member")).toBe(false);
    expect(orgCapability("member")).toBe("student");
  });

  it("defaults to student for unknown/empty roles and no active org", () => {
    expect(isTeacherRole("org:something")).toBe(false);
    expect(isTeacherRole("")).toBe(false);
    expect(isTeacherRole(null)).toBe(false);
    expect(isTeacherRole(undefined)).toBe(false);
    expect(orgCapability("")).toBe("student");
    expect(orgCapability(null)).toBe("student");
    expect(orgCapability(undefined)).toBe("student");
  });
});
