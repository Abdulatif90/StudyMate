import { describe, expect, it } from "vitest";
import { canWriteSharedSubject, isOrgSubject } from "./subjectSharing";

describe("isOrgSubject", () => {
  it("is true when org_id is set", () => {
    expect(isOrgSubject({ org_id: "org_123" })).toBe(true);
  });

  it("is false for a private subject (null or absent org_id)", () => {
    expect(isOrgSubject({ org_id: null })).toBe(false);
    expect(isOrgSubject({})).toBe(false);
  });
});

describe("canWriteSharedSubject", () => {
  it("allows writing any personal subject regardless of capability", () => {
    expect(canWriteSharedSubject(null, "student")).toBe(true);
    expect(canWriteSharedSubject(undefined, "student")).toBe(true);
    expect(canWriteSharedSubject(null, "teacher")).toBe(true);
  });

  it("allows a teacher to write an org subject", () => {
    expect(canWriteSharedSubject("org_123", "teacher")).toBe(true);
  });

  it("blocks a student (member) from writing an org subject", () => {
    expect(canWriteSharedSubject("org_123", "student")).toBe(false);
  });
});
