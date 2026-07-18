import { enUS, koKR, ruRU } from "@clerk/localizations";
import { describe, expect, it } from "vitest";
import { resolveClerkLocalization } from "./clerkLocalization";

describe("resolveClerkLocalization", () => {
  it("resolves English to Clerk's enUS resource", () => {
    expect(resolveClerkLocalization("en")).toBe(enUS);
  });

  it("resolves Korean to Clerk's koKR resource", () => {
    expect(resolveClerkLocalization("ko")).toBe(koKR);
  });

  it("resolves Russian to Clerk's ruRU resource", () => {
    expect(resolveClerkLocalization("ru")).toBe(ruRU);
  });

  it("falls back to enUS for Uzbek (Clerk ships no uz localization)", () => {
    expect(resolveClerkLocalization("uz")).toBe(enUS);
  });
});
