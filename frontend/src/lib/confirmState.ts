export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Styles the confirm button as destructive and defaults its label to "Delete". */
  destructive?: boolean;
}

export interface ConfirmState {
  open: boolean;
  options: ConfirmOptions | null;
}

export const initialConfirmState: ConfirmState = { open: false, options: null };

export function openConfirmState(options: ConfirmOptions): ConfirmState {
  return { open: true, options };
}

/** Close but KEEP the options — the dialog stays mounted through its exit animation, so
 * clearing the text here would blank it mid-transition. */
export function closeConfirmState(state: ConfirmState): ConfirmState {
  return { ...state, open: false };
}

export interface ResolvedConfirmLabels {
  confirmLabel: string;
  cancelLabel: string;
}

/** Fill in the button labels from the options, with sensible defaults: a destructive
 * confirm defaults to "Delete", an ordinary one to "Confirm"; cancel to "Cancel". */
export function resolveConfirmLabels(options: ConfirmOptions): ResolvedConfirmLabels {
  return {
    confirmLabel: options.confirmLabel ?? (options.destructive ? "Delete" : "Confirm"),
    cancelLabel: options.cancelLabel ?? "Cancel",
  };
}
