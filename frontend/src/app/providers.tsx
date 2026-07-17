"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ConfirmProvider } from "@/components/confirm-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster, ToastProvider, toastManager } from "@/components/ui/toast";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <ToastProvider toastManager={toastManager}>
          <ConfirmProvider>
            {children}
            <Toaster />
          </ConfirmProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
