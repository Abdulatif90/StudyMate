import { describe, expect, it } from "vitest";
import {
  closeConfirmState,
  initialConfirmState,
  openConfirmState,
  resolveConfirmLabels,
} from "./confirmState";

describe("confirm state transitions", () => {
  it("starts closed with no options", () => {
    expect(initialConfirmState).toEqual({ open: false, options: null });
  });

  it("opens with the given options", () => {
    const state = openConfirmState({ title: "Delete this?" });
    expect(state.open).toBe(true);
    expect(state.options?.title).toBe("Delete this?");
  });

  it("closes but keeps the options so text survives the exit animation", () => {
    const closed = closeConfirmState(openConfirmState({ title: "Delete this?" }));
    expect(closed.open).toBe(false);
    expect(closed.options?.title).toBe("Delete this?");
  });
});

describe("resolveConfirmLabels", () => {
  it("defaults a destructive confirm to 'Delete'", () => {
    expect(resolveConfirmLabels({ title: "x", destructive: true }).confirmLabel).toBe("Delete");
  });

  it("defaults a non-destructive confirm to 'Confirm'", () => {
    expect(resolveConfirmLabels({ title: "x" }).confirmLabel).toBe("Confirm");
  });

  it("defaults cancel to 'Cancel'", () => {
    expect(resolveConfirmLabels({ title: "x" }).cancelLabel).toBe("Cancel");
  });

  it("respects explicit labels over the defaults", () => {
    expect(
      resolveConfirmLabels({
        title: "x",
        destructive: true,
        confirmLabel: "Remove",
        cancelLabel: "Keep",
      }),
    ).toEqual({ confirmLabel: "Remove", cancelLabel: "Keep" });
  });
});
