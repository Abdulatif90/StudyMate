import { describe, expect, it } from "vitest";
import { simplifyCitations } from "./simplifyCitations";

describe("simplifyCitations", () => {
  it("drops the chunk number but keeps the filename", () => {
    expect(simplifyCitations("Revenue grew (portfolio eng.pdf, chunk 9) significantly.")).toBe(
      "Revenue grew (portfolio eng.pdf) significantly."
    );
  });

  it("simplifies multiple citations across the text", () => {
    expect(
      simplifyCitations("First point (a.pdf, chunk 1). Second point (b.pdf, chunk 12).")
    ).toBe("First point (a.pdf). Second point (b.pdf).");
  });

  it("leaves text with no citations unchanged", () => {
    expect(simplifyCitations("No citations here.")).toBe("No citations here.");
  });
});
