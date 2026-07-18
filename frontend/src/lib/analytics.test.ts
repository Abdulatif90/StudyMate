import { afterEach, describe, expect, it, vi } from "vitest";

const { captureMock } = vi.hoisted(() => ({ captureMock: vi.fn() }));

vi.mock("posthog-js", () => ({
  default: { capture: captureMock },
}));

// captureEvent reads process.env.NEXT_PUBLIC_POSTHOG_KEY at call time, so it must be
// imported AFTER the module mock above is registered (vi.mock is hoisted regardless of
// import order, but the env var itself is read per-call, not at import time).
import { captureEvent } from "./analytics";

describe("captureEvent", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    captureMock.mockClear();
  });

  it("is a no-op when NEXT_PUBLIC_POSTHOG_KEY is unset", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "");
    captureEvent("subjectCreated");
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("fires posthog.capture with the mapped event name when the key is set", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "phc_test");
    captureEvent("subjectCreated");
    expect(captureMock).toHaveBeenCalledWith("subject_created", undefined);
  });

  it("passes properties through untouched", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "phc_test");
    captureEvent("checkoutStarted", { plan: "pro" });
    expect(captureMock).toHaveBeenCalledWith("checkout_started", { plan: "pro" });
  });

  it("maps every declared event name correctly", () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "phc_test");
    captureEvent("documentUploaded");
    captureEvent("quizGenerated");
    captureEvent("flashcardsGenerated");
    captureEvent("questionAsked");
    expect(captureMock).toHaveBeenNthCalledWith(1, "document_uploaded", undefined);
    expect(captureMock).toHaveBeenNthCalledWith(2, "quiz_generated", undefined);
    expect(captureMock).toHaveBeenNthCalledWith(3, "flashcards_generated", undefined);
    expect(captureMock).toHaveBeenNthCalledWith(4, "question_asked", undefined);
  });
});
