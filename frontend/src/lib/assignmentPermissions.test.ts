import { describe, expect, it } from "vitest";
import { canCreateAssignment, canDeleteAssignment } from "./assignmentPermissions";

describe("canCreateAssignment", () => {
  it("allows a teacher", () => {
    expect(canCreateAssignment("teacher")).toBe(true);
  });

  it("denies a student", () => {
    expect(canCreateAssignment("student")).toBe(false);
  });
});

describe("canDeleteAssignment", () => {
  it("allows a teacher, even for another user's assignment", () => {
    expect(canDeleteAssignment("teacher-1", "someone-else", "teacher")).toBe(true);
  });

  it("allows the creator, even as a plain student", () => {
    expect(canDeleteAssignment("student-1", "student-1", "student")).toBe(true);
  });

  it("denies a student who did not create the assignment", () => {
    expect(canDeleteAssignment("student-1", "someone-else", "student")).toBe(false);
  });

  it("denies when the caller id is missing (not yet loaded)", () => {
    expect(canDeleteAssignment(undefined, "someone-else", "student")).toBe(false);
    expect(canDeleteAssignment(null, "someone-else", "student")).toBe(false);
  });
});
