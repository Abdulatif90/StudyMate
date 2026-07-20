import { describe, expect, it } from "vitest";
import { researchSourceLabel } from "./researchSource";

describe("researchSourceLabel", () => {
  it("returns the title when present", () => {
    expect(researchSourceLabel({ title: "MDN Web Docs", url: "https://mdn.io" })).toBe(
      "MDN Web Docs"
    );
  });

  it("falls back to the url when the title is empty", () => {
    expect(researchSourceLabel({ title: "", url: "https://example.com/page" })).toBe(
      "https://example.com/page"
    );
  });

  it("falls back to the url when the title is blank whitespace", () => {
    expect(researchSourceLabel({ title: "   ", url: "https://example.com/page" })).toBe(
      "https://example.com/page"
    );
  });
});
