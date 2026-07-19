import { describe, expect, it } from "vitest";
import { isTeacherRole, orgCapability } from "./orgRole";

describe("orgRole", () => {
  it("treats the admin role as teacher", () => {
    expect(isTeacherRole("org:admin")).toBe(true);
    expect(orgCapability("org:admin")).toBe("teacher");
  });

  it("honors a custom teacher role", () => {
    expect(isTeacherRole("org:teacher")).toBe(true);
    expect(orgCapability("org:teacher")).toBe("teacher");
  });

  it("treats the member role as student", () => {
    expect(isTeacherRole("org:member")).toBe(false);
    expect(orgCapability("org:member")).toBe("student");
  });

  it("defaults to student for unknown roles and no active org", () => {
    expect(isTeacherRole("org:something")).toBe(false);
    expect(isTeacherRole(null)).toBe(false);
    expect(isTeacherRole(undefined)).toBe(false);
    expect(orgCapability(null)).toBe("student");
    expect(orgCapability(undefined)).toBe("student");
  });
});
