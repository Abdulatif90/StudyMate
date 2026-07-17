import { describe, expect, it } from "vitest";
import { parsePlanLimitError } from "./planLimitError";

const body402 = {
  detail: "You've reached your free plan limit of 3 subjects. Upgrade your plan to continue.",
  limit: "subjects",
  plan: "free",
  cap: 3,
};

describe("parsePlanLimitError", () => {
  it("parses a well-formed 402 body into a structured error", () => {
    const parsed = parsePlanLimitError(402, body402);
    expect(parsed).toEqual({
      limit: "subjects",
      plan: "free",
      cap: 3,
      detail: body402.detail,
    });
  });

  it("returns null for a non-402 status even if the body looks like one", () => {
    expect(parsePlanLimitError(422, body402)).toBeNull();
    expect(parsePlanLimitError(500, body402)).toBeNull();
  });

  it("returns null when the body isn't an object", () => {
    expect(parsePlanLimitError(402, null)).toBeNull();
    expect(parsePlanLimitError(402, "nope")).toBeNull();
    expect(parsePlanLimitError(402, undefined)).toBeNull();
  });

  it("returns null when required fields are missing or the wrong type", () => {
    expect(parsePlanLimitError(402, { limit: "subjects", plan: "free" })).toBeNull();
    expect(
      parsePlanLimitError(402, { limit: "subjects", plan: "free", cap: "3" }),
    ).toBeNull();
  });

  it("falls back to a generic detail when the message is missing", () => {
    const parsed = parsePlanLimitError(402, {
      limit: "generations_per_day",
      plan: "pro",
      cap: 200,
    });
    expect(parsed?.detail).toContain("Upgrade");
  });
});
