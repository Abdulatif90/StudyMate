import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";
import { LOCALES, type Locale } from "./locales";
import en from "../../messages/en.json";
import ko from "../../messages/ko.json";
import ru from "../../messages/ru.json";
import uz from "../../messages/uz.json";

type Messages = Record<string, unknown>;

const catalogs: Record<Locale, Messages> = { en, uz, ko, ru };

/** Flatten nested message objects to dotted leaf keys ("Subjects.add"). */
function flatten(obj: Messages, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([key, value]) =>
    typeof value === "string"
      ? [`${prefix}${key}`]
      : flatten(value as Messages, `${prefix}${key}.`),
  );
}

describe("message catalogs", () => {
  it("has a catalog for every declared locale", () => {
    for (const locale of LOCALES) expect(catalogs[locale]).toBeDefined();
  });

  it("keeps identical keys across all locales (no missing/extra strings)", () => {
    const enKeys = flatten(en).sort();
    for (const locale of LOCALES) {
      expect(flatten(catalogs[locale]).sort(), `locale "${locale}" key set`).toEqual(enKeys);
    }
  });

  it("formats the acrossSubjects ICU plural without throwing, per locale and count", () => {
    // The one thing build/en-only tests don't catch: a malformed plural in a non-en
    // catalog only errors when that locale is actually loaded at runtime.
    for (const locale of LOCALES) {
      // createTranslator infers message keys from the (loosely typed) catalog, which
      // narrows them to `never` here — assert a plain callable to format by dotted key.
      const translate = createTranslator({
        locale,
        messages: catalogs[locale],
      }) as unknown as (key: string, values?: Record<string, number | string>) => string;
      for (const count of [0, 1, 2, 5, 11, 21, 100]) {
        expect(typeof translate("Dashboard.acrossSubjects", { count })).toBe("string");
      }
    }
  });
});
