import { describe, expect, it } from "vitest";
import { friendlyUploadError } from "./uploadError";

describe("friendlyUploadError", () => {
  it("maps 415 to an unsupported-file-type message", () => {
    expect(friendlyUploadError(415)).toMatch(/isn't supported/);
  });

  it("maps 413 to a too-large message", () => {
    expect(friendlyUploadError(413)).toMatch(/too large/);
  });

  it("falls back to a generic message for any other status", () => {
    expect(friendlyUploadError(500)).toBe("Couldn't upload the file. Please try again.");
  });
});
