import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, isLocale, LOCALES, resolveLocale } from "./locales";

describe("isLocale", () => {
  it("accepts every supported locale", () => {
    for (const locale of LOCALES) expect(isLocale(locale)).toBe(true);
  });

  it("rejects unknown or non-string values", () => {
    expect(isLocale("de")).toBe(false);
    expect(isLocale("EN")).toBe(false); // case-sensitive on purpose
    expect(isLocale("")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
    expect(isLocale(null)).toBe(false);
    expect(isLocale(42)).toBe(false);
  });
});

describe("resolveLocale", () => {
  it("returns a supported locale unchanged", () => {
    expect(resolveLocale("ko")).toBe("ko");
    expect(resolveLocale("ru")).toBe("ru");
    expect(resolveLocale("uz")).toBe("uz");
  });

  it("falls back to the default for unknown/missing/malformed values", () => {
    expect(resolveLocale("de")).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(undefined)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(null)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale("")).toBe(DEFAULT_LOCALE);
    expect(resolveLocale("../../etc/passwd")).toBe(DEFAULT_LOCALE);
  });

  it("defaults specifically to en (guards the dynamic catalog import)", () => {
    expect(DEFAULT_LOCALE).toBe("en");
    expect(resolveLocale("xx")).toBe("en");
  });
});
