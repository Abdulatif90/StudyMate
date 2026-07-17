import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LanguageSwitcher } from "./language-switcher";
import { LOCALES } from "@/i18n/locales";
import { setLocale } from "@/i18n/setLocale";
import { renderWithIntl } from "@/lib/test/renderWithIntl";

// The switcher depends on the App Router and a server action; both are stubbed so the
// component can render in jsdom. setLocale is imported (mocked) below to assert the wiring.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("@/i18n/setLocale", () => ({
  setLocale: vi.fn(),
}));

describe("LanguageSwitcher", () => {
  it("renders one option per supported locale", () => {
    renderWithIntl(<LanguageSwitcher />);
    const select = screen.getByRole("combobox", { name: "Language" });
    expect(within(select).getAllByRole("option")).toHaveLength(LOCALES.length);
  });

  it("reflects the active locale as the selected value", () => {
    renderWithIntl(<LanguageSwitcher />, { locale: "ru" });
    const select = screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement;
    expect(select.value).toBe("ru");
  });

  it("calls setLocale with the chosen locale on change", async () => {
    renderWithIntl(<LanguageSwitcher />);
    const select = screen.getByRole("combobox", { name: "Language" });
    fireEvent.change(select, { target: { value: "ko" } });
    await waitFor(() => expect(setLocale).toHaveBeenCalledWith("ko"));
  });
});
