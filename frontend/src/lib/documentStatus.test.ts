import { describe, expect, it } from "vitest";
import { documentStatusVariant } from "./documentStatus";

describe("documentStatusVariant", () => {
  it("maps ready to default", () => {
    expect(documentStatusVariant("ready")).toBe("default");
  });

  it("maps failed to destructive", () => {
    expect(documentStatusVariant("failed")).toBe("destructive");
  });

  it("maps pending to secondary", () => {
    expect(documentStatusVariant("pending")).toBe("secondary");
  });
});
