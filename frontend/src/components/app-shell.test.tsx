import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";
import { renderWithIntl } from "@/lib/test/renderWithIntl";

// AppShell depends on Clerk's account widget/user data, the App Router's pathname
// hook, and a billing-plan fetch — all stubbed so the component can render in jsdom
// (same reasoning as language-switcher.test.tsx stubbing next/navigation).
// usePathname is a mutable var so each test can pick its own route.
let currentPathname = "/dashboard";
vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({
  UserButton: () => <div data-testid="user-button" />,
  useUser: () => ({ user: { fullName: "Ada Lovelace", primaryEmailAddress: null } }),
}));
// The sidebar's usage widget + profile row both call useQuery for GET /billing/plan —
// mocked directly (rather than wrapping in a real QueryClientProvider) to keep this
// consistent with how the rest of this file already stubs its dependencies.
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: {
      plan: "free",
      limits: { max_subjects: 3, max_documents_per_subject: 10, max_generations_per_day: 20 },
      usage: { subjects: 1, generations_today: 2 },
    },
  }),
}));
vi.mock("@/lib/api/useApiClient", () => ({
  useApiClient: () => ({ GET: vi.fn() }),
}));

describe("AppShell", () => {
  it("renders every primary destination as a link to the right URL", () => {
    currentPathname = "/dashboard";
    renderWithIntl(<AppShell>content</AppShell>);
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: /subjects/i })).toHaveAttribute("href", "/subjects");
    expect(screen.getByRole("link", { name: /plan & billing/i })).toHaveAttribute(
      "href",
      "/billing",
    );
  });

  it("marks the destination matching the current pathname as the active page", () => {
    currentPathname = "/subjects/abc123/quizzes";
    renderWithIntl(<AppShell>content</AppShell>);
    expect(screen.getByRole("link", { name: /subjects/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /dashboard/i })).not.toHaveAttribute("aria-current");
  });

  it("renders the account widget and children", () => {
    currentPathname = "/dashboard";
    renderWithIntl(<AppShell>page content</AppShell>);
    // Rendered twice — once in the desktop sidebar, once in the mobile top bar — both
    // exist in the DOM in this jsdom environment (no real CSS engine to evaluate the
    // lg: breakpoint that would otherwise hide one of them), so this asserts presence,
    // not count.
    expect(screen.getAllByTestId("user-button").length).toBeGreaterThan(0);
    expect(screen.getByText("page content")).toBeInTheDocument();
  });

  it("shows the signed-in user's name and plan in the sidebar profile row", () => {
    currentPathname = "/dashboard";
    renderWithIntl(<AppShell>content</AppShell>);
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Free")).toBeInTheDocument();
  });
});
