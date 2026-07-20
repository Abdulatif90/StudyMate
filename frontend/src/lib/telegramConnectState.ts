/**
 * Pure view-state resolver for the dashboard's "Connect Telegram" card — kept separate
 * from the fetching component so the branching logic (loading / error / connected /
 * not-yet-connected) is unit-testable without a QueryClient or Clerk provider.
 */
export type TelegramConnectState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "connected" }
  | { kind: "connect"; deepLink: string | null };

export function telegramConnectState(params: {
  statusLoading: boolean;
  statusError: boolean;
  linked: boolean | undefined;
  deepLink: string | undefined;
}): TelegramConnectState {
  if (params.statusLoading) return { kind: "loading" };
  if (params.statusError) return { kind: "error" };
  if (params.linked) return { kind: "connected" };
  return { kind: "connect", deepLink: params.deepLink ?? null };
}
