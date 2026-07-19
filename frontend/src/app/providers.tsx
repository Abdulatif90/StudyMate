"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostHogProvider } from "posthog-js/react";
import { useState } from "react";
import { ConfirmProvider } from "@/components/confirm-provider";
import { ObservabilityIdentity } from "@/components/observability-identity";
import { ReferralCapture } from "@/components/referral-capture";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster, ToastProvider, toastManager } from "@/components/ui/toast";

/**
 * Wraps `children` in `PostHogProvider` only when `NEXT_PUBLIC_POSTHOG_KEY` is set —
 * rendering the provider unconditionally with an empty `apiKey` still logs a console
 * warning and falls back to an unmanaged global instance (see posthog-js/react's own
 * source), which isn't the clean "simply off" behavior this app's other optional
 * integrations have. Skipping the provider entirely avoids that.
 */
function Analytics({ children }: { children: React.ReactNode }) {
  const apiKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!apiKey) return <>{children}</>;

  return (
    <PostHogProvider
      apiKey={apiKey}
      options={{
        api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com",
        // A small, deliberate event set is captured explicitly instead (see
        // src/lib/analytics.ts) — not PostHog's own DOM-click/element autocapture.
        autocapture: false,
        respect_dnt: true,
      }}
    >
      {children}
    </PostHogProvider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <Analytics>
        <QueryClientProvider client={queryClient}>
          <ToastProvider toastManager={toastManager}>
            <ConfirmProvider>
              <ObservabilityIdentity />
              <ReferralCapture />
              {children}
              <Toaster />
            </ConfirmProvider>
          </ToastProvider>
        </QueryClientProvider>
      </Analytics>
    </ThemeProvider>
  );
}
