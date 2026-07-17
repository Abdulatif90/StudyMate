"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  closeConfirmState,
  initialConfirmState,
  openConfirmState,
  resolveConfirmLabels,
  type ConfirmOptions,
  type ConfirmState,
} from "@/lib/confirmState";

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * Mounts a single shared confirmation dialog and exposes `useConfirm()` — an imperative,
 * promise-based replacement for `window.confirm` (FRONTEND.md §3.1).
 *
 * The choice is recorded in `resultRef` on button click and the promise is settled exactly
 * once, in `onOpenChange`, when the dialog actually closes — so it doesn't matter whether
 * the button's onClick or Base UI's close fires first, and an Esc/outside dismiss settles
 * to `false` (the ref's default).
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState>(initialConfirmState);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);
  const resultRef = useRef(false);

  const settle = useCallback((result: boolean) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setState(closeConfirmState);
  }, []);

  const confirm = useCallback<ConfirmFn>((options) => {
    // Resolve any still-pending confirm as cancelled before opening a new one.
    resolverRef.current?.(false);
    resultRef.current = false;
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState(openConfirmState(options));
    });
  }, []);

  const labels = state.options ? resolveConfirmLabels(state.options) : null;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog
        open={state.open}
        onOpenChange={(open) => {
          if (!open) {
            settle(resultRef.current);
            resultRef.current = false;
          }
        }}
      >
        {state.options && labels ? (
          <AlertDialogContent>
            <AlertDialogTitle>{state.options.title}</AlertDialogTitle>
            {state.options.description ? (
              <AlertDialogDescription>{state.options.description}</AlertDialogDescription>
            ) : null}
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => (resultRef.current = false)}>
                {labels.cancelLabel}
              </AlertDialogCancel>
              <AlertDialogAction
                destructive={state.options.destructive}
                onClick={() => (resultRef.current = true)}
              >
                {labels.confirmLabel}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        ) : null}
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within <ConfirmProvider>");
  return ctx;
}
