import type { Metadata } from "next";

import { PublicLanding } from "@/components/public-landing";

export const metadata: Metadata = {
  title: "AI Agent Action Control Plane",
  description: "Intercept risky AI agent actions, enforce policy, verify outcomes in the system of record, and issue durable proof.",
};

export default function HomePage() {
  return <PublicLanding />;
}
