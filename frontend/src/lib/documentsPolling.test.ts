import { describe, expect, it } from "vitest";
import { DOCUMENTS_POLL_INTERVAL_MS, documentsRefetchInterval } from "./documentsPolling";
import type { components } from "@/lib/api/schema";

type DocumentRead = components["schemas"]["DocumentRead"];

function doc(status: DocumentRead["status"]): DocumentRead {
  return {
    id: crypto.randomUUID(),
    subject_id: crypto.randomUUID(),
    filename: "f.txt",
    content_type: "text/plain",
    status,
    created_at: "2026-07-16T00:00:00Z",
  };
}

describe("documentsRefetchInterval", () => {
  it("polls while any document is pending", () => {
    expect(documentsRefetchInterval([doc("ready"), doc("pending")])).toBe(
      DOCUMENTS_POLL_INTERVAL_MS
    );
  });

  it("stops polling once all documents are settled", () => {
    expect(documentsRefetchInterval([doc("ready"), doc("failed")])).toBe(false);
  });

  it("does not poll an empty list", () => {
    expect(documentsRefetchInterval([])).toBe(false);
  });

  it("does not poll when data is absent", () => {
    expect(documentsRefetchInterval(undefined)).toBe(false);
  });
});
