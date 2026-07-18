import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";
import { renderWithIntl } from "@/lib/test/renderWithIntl";

// AppShell depends on Clerk's account widget and the App Router's pathname hook; both are
// stubbed so the component can render in jsdom (same reasoning as language-switcher.test.tsx
// stubbing next/navigation). usePathname is a mutable var so each test can pick its own route.
let currentPathname = "/dashboard";
vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({
  UserButton: () => <div data-testid="user-button" />,
}));

describe("AppShell", () => {
  // Base UI's Button renders an `<a>` here (via `render={<Link .../>}`) but keeps
  // `role="button"` rather than the anchor's native "link" role — matching the same
  // convention already used for CTA buttons elsewhere in this codebase (e.g. the home
  // page's "Go to Subjects" button), so these are queried as buttons, not links.
  it("renders every primary destination as a button linking to the right URL", () => {
    currentPathname = "/dashboard";
    renderWithIntl(<AppShell>content</AppShell>);
    expect(screen.getByRole("button", { name: /dashboard/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(screen.getByRole("button", { name: /subjects/i })).toHaveAttribute(
      "href",
      "/subjects",
    );
    expect(screen.getByRole("button", { name: /plan & billing/i })).toHaveAttribute(
      "href",
      "/billing",
    );
  });

  it("marks the destination matching the current pathname as the active page", () => {
    currentPathname = "/subjects/abc123/quizzes";
    renderWithIntl(<AppShell>content</AppShell>);
    expect(screen.getByRole("button", { name: /subjects/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: /dashboard/i })).not.toHaveAttribute("aria-current");
  });

  it("renders the account widget and children", () => {
    currentPathname = "/dashboard";
    renderWithIntl(<AppShell>page content</AppShell>);
    expect(screen.getByTestId("user-button")).toBeInTheDocument();
    expect(screen.getByText("page content")).toBeInTheDocument();
  });
});
