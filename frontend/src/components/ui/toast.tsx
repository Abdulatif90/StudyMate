"use client";

import { Toast as ToastPrimitive } from "@base-ui/react/toast";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { ComponentType } from "react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "error" | "warning" | "info";

/**
 * Global toast manager. Created outside React so `toast()` can be called from anywhere —
 * including TanStack Query mutation callbacks — not just inside components. Mounted via
 * `<ToastProvider toastManager={toastManager}>` in app/providers.tsx.
 */
export const toastManager = ToastPrimitive.createToastManager();
export const ToastProvider = ToastPrimitive.Provider;

interface ToastOptions {
  title?: string;
  description?: string;
  type?: ToastType;
  /** ms before auto-dismiss; 0 disables it. Base UI default is 5000. */
  timeout?: number;
  /** Optional action button (e.g. an "Upgrade" CTA mirroring the 402 prompt). */
  action?: { label: string; onClick: () => void };
}

function baseToast({ title, description, type = "info", timeout, action }: ToastOptions) {
  return toastManager.add({
    title,
    description,
    type,
    timeout,
    actionProps: action ? { children: action.label, onClick: action.onClick } : undefined,
  });
}

/** Fire a toast. `toast.success(...)` / `.error(...)` / `.warning(...)` are shorthands. */
export const toast = Object.assign(baseToast, {
  success: (title: string, description?: string) =>
    baseToast({ title, description, type: "success" }),
  error: (title: string, description?: string) =>
    baseToast({ title, description, type: "error" }),
  warning: (title: string, description?: string) =>
    baseToast({ title, description, type: "warning" }),
});

// Colour is paired with an icon per type (never colour alone — FRONTEND.md §2.5).
const TYPE_ICON: Record<ToastType, ComponentType<{ className?: string }>> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const TYPE_ACCENT: Record<ToastType, string> = {
  success: "text-success",
  error: "text-destructive",
  warning: "text-warning",
  info: "text-primary",
};

/**
 * Renders the live toasts. Mount once, inside `<ToastProvider>` (see app/providers.tsx).
 * Fixed bottom-right on desktop, full-width bottom on mobile; each toast is focus-managed
 * and Esc/swipe dismissable by Base UI.
 */
export function Toaster() {
  const { toasts } = ToastPrimitive.useToastManager();

  return (
    <ToastPrimitive.Portal>
      <ToastPrimitive.Viewport className="fixed right-0 bottom-0 z-50 flex w-full flex-col gap-2 p-4 sm:right-4 sm:bottom-4 sm:w-90 sm:p-0">
        {toasts.map((item) => {
          const type = (item.type as ToastType) ?? "info";
          const Icon = TYPE_ICON[type] ?? Info;
          return (
            <ToastPrimitive.Root
              key={item.id}
              toast={item}
              className={cn(
                "flex items-start gap-3 rounded-lg border border-border bg-card p-4 shadow-lg",
                "data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 transition-opacity",
              )}
            >
              <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0", TYPE_ACCENT[type])} />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                {item.title ? (
                  <ToastPrimitive.Title className="text-sm font-medium text-card-foreground" />
                ) : null}
                {item.description ? (
                  <ToastPrimitive.Description className="text-sm text-muted-foreground" />
                ) : null}
                {item.actionProps ? (
                  <ToastPrimitive.Action className="mt-1 w-fit rounded-md text-sm font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none" />
                ) : null}
              </div>
              <ToastPrimitive.Close
                aria-label="Dismiss"
                className="rounded-md p-0.5 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <X className="size-4" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          );
        })}
      </ToastPrimitive.Viewport>
    </ToastPrimitive.Portal>
  );
}
