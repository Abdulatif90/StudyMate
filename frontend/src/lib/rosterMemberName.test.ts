import { describe, expect, it } from "vitest";
import { resolveMemberName } from "./rosterMemberName";

describe("resolveMemberName", () => {
  it("prefers the member's full name when both first and last are present", () => {
    const memberships = [
      {
        publicUserData: {
          userId: "user_1",
          identifier: "jane@example.com",
          firstName: "Jane",
          lastName: "Doe",
        },
      },
    ];
    expect(resolveMemberName("user_1", memberships)).toBe("Jane Doe");
  });

  it("falls back to just the first name when there's no last name", () => {
    const memberships = [
      {
        publicUserData: {
          userId: "user_1",
          identifier: "jane@example.com",
          firstName: "Jane",
          lastName: null,
        },
      },
    ];
    expect(resolveMemberName("user_1", memberships)).toBe("Jane");
  });

  it("falls back to the identifier when no name is set", () => {
    const memberships = [
      {
        publicUserData: {
          userId: "user_1",
          identifier: "jane@example.com",
          firstName: null,
          lastName: null,
        },
      },
    ];
    expect(resolveMemberName("user_1", memberships)).toBe("jane@example.com");
  });

  it("falls back to a shortened id when the member isn't in the list", () => {
    expect(resolveMemberName("user_2c9f8a1b7e6d", [])).toBe("user_2c9…");
  });

  it("falls back to a shortened id when memberships is null/undefined", () => {
    expect(resolveMemberName("user_2c9f8a1b7e6d", null)).toBe("user_2c9…");
    expect(resolveMemberName("user_2c9f8a1b7e6d", undefined)).toBe("user_2c9…");
  });

  it("falls back to a shortened id when publicUserData is missing entirely", () => {
    expect(resolveMemberName("user_2c9f8a1b7e6d", [{}])).toBe("user_2c9…");
  });
});
