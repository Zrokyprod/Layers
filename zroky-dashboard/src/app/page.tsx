import type { Metadata } from "next";

import { PublicFooter, PublicNav } from "@/components/public-chrome";
import LandingProofLoop from "@/components/landing-proof-loop";

export const metadata: Metadata = {
  title: "Zroky - Prove AI agent fixes before they ship",
  description:
    "Capture failed production AI-agent runs, diagnose root cause, replay exact scenarios, and block regressions with CI gates.",
};

export default function HomePage() {
  return (
    <main className="z-public zl-public">
      <PublicNav />
      <LandingProofLoop />
      <section className="zl-final-cta">
        <span className="zl-section-label">Verified release gates</span>
        <h2>Turn the next failed agent run into a CI gate.</h2>
        <p>Start with capture. Prove the fix. Keep regressions out of production.</p>
        <a href="/signup" className="zl-button zl-button-primary">
          Start free
        </a>
      </section>
      <PublicFooter />
    </main>
  );
}
