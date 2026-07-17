# Message catalogs (next-intl)

- **`en.json` is the source of truth.** Add every new string here first, then mirror the
  same keys into `uz.json`, `ko.json`, `ru.json`. Keep the key structure identical across
  all four files.
- **`uz.json` / `ko.json` / `ru.json` are machine/LLM-drafted starting points and still
  need review by a native speaker before they can be called production-quality.** In
  particular the ICU `plural` forms (e.g. `Dashboard.acrossSubjects`) follow each
  language's CLDR categories but the exact wording/case agreement — especially Russian
  `few`/`many` and the `по` + dative phrasing — is best-effort and likely needs fixing.
- Locales are declared in `src/i18n/locales.ts`. Adding one there **and** adding a
  matching catalog file is all that's needed — there is no URL routing to touch (next-intl
  "without i18n routing" mode; the active locale lives in the `locale` cookie).
