import type { Metadata } from "next";

import { PublicLanding } from "@/components/public-landing";

export const metadata: Metadata = {
  title: "AI Agent Reliability Control Plane",
  description:
    "Zroky turns failed AI-agent runs into trace evidence, replay proof, golden contracts, CI gates, and release readiness.",
};

export default function HomePage() {
  return <PublicLanding />;
}
