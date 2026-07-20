import { describe, expect, it } from "vitest";
import { telegramConnectState } from "./telegramConnectState";

describe("telegramConnectState", () => {
  it("is loading while the status query is in flight", () => {
    expect(
      telegramConnectState({
        statusLoading: true,
        statusError: false,
        linked: undefined,
        deepLink: undefined,
      }),
    ).toEqual({ kind: "loading" });
  });

  it("is error when the status query fails, even if loading also somehow flipped", () => {
    expect(
      telegramConnectState({
        statusLoading: false,
        statusError: true,
        linked: undefined,
        deepLink: undefined,
      }),
    ).toEqual({ kind: "error" });
  });

  it("is connected once status reports linked", () => {
    expect(
      telegramConnectState({
        statusLoading: false,
        statusError: false,
        linked: true,
        deepLink: undefined,
      }),
    ).toEqual({ kind: "connected" });
  });

  it("is connect with a null deepLink while the link code is still being minted", () => {
    expect(
      telegramConnectState({
        statusLoading: false,
        statusError: false,
        linked: false,
        deepLink: undefined,
      }),
    ).toEqual({ kind: "connect", deepLink: null });
  });

  it("is connect with the deepLink once the link code has arrived", () => {
    expect(
      telegramConnectState({
        statusLoading: false,
        statusError: false,
        linked: false,
        deepLink: "https://t.me/helperstudymatebot?start=ABC123",
      }),
    ).toEqual({ kind: "connect", deepLink: "https://t.me/helperstudymatebot?start=ABC123" });
  });
});
