import { describe, expect, it } from "vitest";
import { friendlyDeleteError } from "./deleteError";

describe("friendlyDeleteError", () => {
  it("maps 404 to an already-gone message", () => {
    expect(friendlyDeleteError(404)).toMatch(/already deleted|couldn't be found/);
  });

  it("falls back to a generic message for any other status", () => {
    expect(friendlyDeleteError(500)).toBe("Couldn't delete this document. Please try again.");
  });
});
