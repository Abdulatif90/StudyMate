import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import enMessages from "../../messages/en.json";

// The upload card (and its size hint) only needs the subject query to resolve to a
// personal, writable subject; the documents query can be empty.
const getSpy = vi.fn(async (url: string) => {
  if (url === "/subjects/{subject_id}") {
    return { data: { id: "s1", name: "Biology", org_id: null }, error: null };
  }
  return { data: [], error: null };
});

vi.mock("@/lib/api/useApiClient", () => ({
  useApiClient: () => ({ GET: getSpy, POST: vi.fn(), DELETE: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({
  useOrganization: () => ({ organization: null, membership: null }),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ subjectId: "s1" }),
}));
vi.mock("@/components/confirm-provider", () => ({ useConfirm: () => vi.fn() }));
vi.mock("@/components/ui/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("@/lib/analytics", () => ({ captureEvent: vi.fn() }));

import SubjectDetailPage from "@/app/(app)/subjects/[subjectId]/page";

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

describe("SubjectDetailPage upload hint", () => {
  it("renders the always-visible max-size hint with the 20 MB limit", async () => {
    render(<SubjectDetailPage />, { wrapper: Wrapper });

    // The hint drives its number from the shared MAX_UPLOAD_MB constant.
    expect(await screen.findByText("Max 20 MB per file")).toBeInTheDocument();
  });
});
