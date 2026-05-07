import type { ReactNode } from "react";

import { DashboardShell } from "@/components/dashboard-shell";
import { AssistantChat } from "@/components/assistant-chat";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <DashboardShell>
      {children}
      <AssistantChat />
    </DashboardShell>
  );
}
