import { describe, expect, it } from "vitest";
import { friendlyFlashcardError } from "./flashcardError";

describe("friendlyFlashcardError", () => {
  it("maps 422 to an actionable no-material message", () => {
    expect(friendlyFlashcardError(422)).toMatch(/no processed material/i);
    expect(friendlyFlashcardError(422)).toMatch(/upload/i);
  });

  it("maps 502 to a retryable generation-failure message", () => {
    expect(friendlyFlashcardError(502)).toMatch(/try again/i);
  });

  it("falls back to a generic message for any other status", () => {
    expect(friendlyFlashcardError(500)).toMatch(/something went wrong/i);
  });
});
