import { describe, expect, it } from "vitest";
import { classifyRosterError } from "./rosterStatus";

describe("classifyRosterError", () => {
  it("classifies 503 as unavailable (Clerk not configured)", () => {
    expect(classifyRosterError(503)).toBe("unavailable");
  });

  it("classifies 502 as gateway (upstream Clerk failure)", () => {
    expect(classifyRosterError(502)).toBe("gateway");
  });

  it("classifies any other status as other", () => {
    expect(classifyRosterError(404)).toBe("other");
    expect(classifyRosterError(403)).toBe("other");
    expect(classifyRosterError(500)).toBe("other");
  });

  it("classifies an undefined status as other", () => {
    expect(classifyRosterError(undefined)).toBe("other");
  });
});
