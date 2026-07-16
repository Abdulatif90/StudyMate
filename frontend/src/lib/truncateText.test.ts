import { describe, expect, it } from "vitest";
import { truncateText } from "./truncateText";

describe("truncateText", () => {
  it("returns short text unchanged", () => {
    expect(truncateText("Hello", 10)).toBe("Hello");
  });

  it("truncates long text and appends an ellipsis", () => {
    expect(truncateText("This is a long question about biology", 10)).toBe("This is a…");
  });

  it("returns text unchanged when exactly at the limit", () => {
    expect(truncateText("Exactly10!", 10)).toBe("Exactly10!");
  });
});
