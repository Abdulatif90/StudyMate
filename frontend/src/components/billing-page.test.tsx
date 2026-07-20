import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import enMessages from "../../messages/en.json";

// A checkout POST that stays pending until we resolve it, so the in-flight ("Redirecting…")
// state can be inspected across ALL plan cards, not just the clicked one.
let resolvePost: (v: unknown) => void = () => {};
const postSpy = vi.fn(
  (..._args: unknown[]) =>
    new Promise((res) => {
      resolvePost = res;
    }),
);
const getSpy = vi.fn(async () => ({
  data: {
    plan: "free",
    limits: { max_subjects: 3, max_documents_per_subject: 10, max_generations_per_day: 20 },
    usage: { subjects: 1, generations_today: 2 },
  },
  error: null,
}));

vi.mock("@/lib/api/useApiClient", () => ({
  useApiClient: () => ({ GET: getSpy, POST: postSpy }),
}));
vi.mock("@clerk/nextjs", () => ({
  useOrganization: () => ({ organization: null, membership: null }),
}));
vi.mock("@/lib/analytics", () => ({ captureEvent: vi.fn() }));

import BillingPage from "@/app/(app)/billing/page";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <NextIntlClientProvider locale="en" messages={enMessages}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("BillingPage checkout", () => {
  beforeEach(() => {
    postSpy.mockClear();
    Object.defineProperty(window, "location", {
      value: { origin: "http://localhost", href: "" },
      writable: true,
    });
  });

  it("clicking one plan fires exactly one checkout with the clicked plan", async () => {
    const user = userEvent.setup();
    render(<BillingPage />, { wrapper: Wrapper });
    await waitFor(() => screen.getByRole("button", { name: /upgrade to pro/i }));

    await user.click(screen.getByRole("button", { name: /upgrade to pro/i }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1));
    expect(postSpy.mock.calls[0][1]).toMatchObject({ body: { plan: "pro" } });
    resolvePost({ data: { checkout_url: "x" }, error: null });
  });

  it("shows the pending state only on the clicked card, leaving the other upgrade enabled", async () => {
    const user = userEvent.setup();
    render(<BillingPage />, { wrapper: Wrapper });
    await waitFor(() => screen.getByRole("button", { name: /upgrade to pro/i }));

    await user.click(screen.getByRole("button", { name: /upgrade to pro/i }));

    // Clicked (Pro) card: redirecting + disabled.
    const pro = await screen.findByRole("button", { name: /redirecting/i });
    expect(pro).toBeDisabled();
    // Other upgrade (Business) card: still its normal label AND still enabled — a
    // pending Pro checkout must not disable/activate the Business button too.
    const business = screen.getByRole("button", { name: /upgrade to business/i });
    expect(business).not.toBeDisabled();

    resolvePost({ data: { checkout_url: "x" }, error: null });
  });
});
