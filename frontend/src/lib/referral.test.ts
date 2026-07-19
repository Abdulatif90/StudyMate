import { describe, expect, it } from "vitest";
import { buildReferralShareUrl, parseRefParam } from "@/lib/referral";

describe("parseRefParam", () => {
  it("returns a well-formed code from the query string", () => {
    expect(parseRefParam("?ref=ABCD2345")).toBe("ABCD2345");
  });

  it("normalizes case to uppercase", () => {
    expect(parseRefParam("?ref=abcd2345")).toBe("ABCD2345");
  });

  it("trims surrounding whitespace", () => {
    expect(parseRefParam("?ref=%20ABCD2345%20")).toBe("ABCD2345");
  });

  it("returns null when there is no ref param", () => {
    expect(parseRefParam("?other=1")).toBeNull();
    expect(parseRefParam("")).toBeNull();
  });

  it("rejects malformed codes (wrong length, illegal chars)", () => {
    expect(parseRefParam("?ref=ABC")).toBeNull(); // too short
    expect(parseRefParam("?ref=ABCD23456")).toBeNull(); // too long
    expect(parseRefParam("?ref=ABCD2019")).toBeNull(); // 0,1,9 not in base32 alphabet
    expect(parseRefParam("?ref=../../etc")).toBeNull(); // path-traversal-ish garbage
  });

  it("reads ref among other params", () => {
    expect(parseRefParam("?utm=x&ref=WXYZ7654&a=b")).toBe("WXYZ7654");
  });
});

describe("buildReferralShareUrl", () => {
  it("builds a sign-up URL carrying the code", () => {
    expect(buildReferralShareUrl("https://app.example.com", "ABCD2345")).toBe(
      "https://app.example.com/sign-up?ref=ABCD2345",
    );
  });

  it("round-trips through parseRefParam", () => {
    const url = buildReferralShareUrl("https://app.example.com", "WXYZ7654");
    const search = url.slice(url.indexOf("?"));
    expect(parseRefParam(search)).toBe("WXYZ7654");
  });
});
