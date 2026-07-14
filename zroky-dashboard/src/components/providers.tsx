"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect, useState } from "react";

import { AUTH_SESSION_CHANGED_EVENT } from "@/lib/auth";
import { useDashboardStore } from "@/lib/store";
import { ErrorBoundary } from "./error-boundary";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 3,
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
          },
        },
      })
  );

  useEffect(() => {
    function resetAccountBoundState() {
      queryClient.clear();
      useDashboardStore.getState().setSelectedProject(null);
    }

    window.addEventListener(AUTH_SESSION_CHANGED_EVENT, resetAccountBoundState);
    return () => window.removeEventListener(AUTH_SESSION_CHANGED_EVENT, resetAccountBoundState);
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light" enableSystem={false}>
        <ErrorBoundary>{children}</ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
