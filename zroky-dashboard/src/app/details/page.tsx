import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Database, GitBranch, LockKeyhole, Radar, Workflow } from "lucide-react";
import { PublicFooter, PublicNav } from "@/components/public-chrome";

export const metadata: Metadata = {
  title: "Details",
  description: "Product details for the Zroky AI agent reliability dashboard.",
};

const sections = [
  {
    id: "dashboard",
    title: "Dashboard modules",
    icon: Workflow,
    body: "Agents, Issues, Replay, Goldens, Drift, Cost, Alerts, and Settings are organized around the next operational decision.",
  },
  {
    id: "release-loop",
    title: "Release loop",
    icon: GitBranch,
    body: "A production incident can become a replay, a verified fix, and a release gate that blocks regressions before deploy.",
  },
  {
    id: "evidence",
    title: "Evidence model",
    icon: Database,
    body: "Prompt versions, tool calls, retrieval chunks, model responses, latency, cost, and outcomes stay linked to the issue.",
  },
  {
    id: "security",
    title: "Security posture",
    icon: LockKeyhole,
    body: "Project-scoped access, audit trails, provider-key controls, and retention rules are treated as core product surfaces.",
  },
];

export default function DetailsPage() {
  return (
    <main className="public-site public-subpage">
      <PublicNav />

      <section className="public-subpage-hero">
        <span className="public-kicker">Product details</span>
        <h1>Everything behind the Zroky dashboard.</h1>
        <p>
          The product is planned as an operating system for agent reliability: issue grouping, replay proof, release
          gates, drift review, and cost visibility all connected to the same evidence trail.
        </p>
        <Link href="/auth/register" className="public-primary-button public-primary-button-lg">
          Get Started
          <ArrowRight aria-hidden="true" />
        </Link>
      </section>

      <section className="public-section public-details-grid">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <article key={section.id} id={section.id}>
              <Icon aria-hidden="true" />
              <h2>{section.title}</h2>
              <p>{section.body}</p>
              <span>
                <CheckCircle2 aria-hidden="true" />
                Built for production review, not screenshots.
              </span>
            </article>
          );
        })}
      </section>

      <section className="public-section public-split-section">
        <div>
          <span className="public-kicker">Operating model</span>
          <h2>One issue should answer four questions.</h2>
          <p>
            What happened, why it matters, what proof exists, and what action should happen next. That rule drives the
            page structure across the product.
          </p>
        </div>
        <div className="public-page-grid">
          {["Incident evidence", "Replay comparison", "Fix PR readiness", "Golden promotion"].map((item) => (
            <span key={item} className="public-static-tile">
              <Radar aria-hidden="true" />
              {item}
            </span>
          ))}
        </div>
      </section>

      <PublicFooter />
    </main>
  );
}
