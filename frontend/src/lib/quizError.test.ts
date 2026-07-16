import { describe, expect, it } from "vitest";
import { friendlyQuizError } from "./quizError";

describe("friendlyQuizError", () => {
  it("maps 422 to an actionable no-material message", () => {
    expect(friendlyQuizError(422)).toMatch(/no processed material/i);
    expect(friendlyQuizError(422)).toMatch(/upload/i);
  });

  it("maps 502 to a retryable generation-failure message", () => {
    expect(friendlyQuizError(502)).toMatch(/try again/i);
  });

  it("falls back to a generic message for any other status", () => {
    expect(friendlyQuizError(500)).toMatch(/something went wrong/i);
  });
});
