import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldCheck, UsersRound, Zap } from "lucide-react";
import { PublicFooter, PublicNav } from "@/components/public-chrome";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Zroky pricing paths for free workspaces, team rollouts, and enterprise controls.",
};

const plans = [
  {
    name: "Starter",
    price: "Free workspace",
    body: "For first agent capture, issue review, and replay workflow validation.",
    icon: Zap,
    bullets: ["Create a workspace", "Connect first agent", "Review issues", "Start replay flow"],
  },
  {
    name: "Team",
    price: "Team rollout",
    body: "For production teams that need owners, release gates, and shared operational review.",
    icon: UsersRound,
    bullets: ["Team issue queue", "Replay comparison", "Golden promotion", "Release gate review"],
  },
  {
    name: "Enterprise",
    price: "Custom",
    body: "For organizations that need security controls, auditability, and deeper rollout support.",
    icon: ShieldCheck,
    bullets: ["Scoped access", "Audit trails", "Retention controls", "Deployment support"],
  },
];

export default function PricingPage() {
  return (
    <main className="public-site public-subpage">
      <PublicNav />

      <section className="public-subpage-hero">
        <span className="public-kicker">Pricing</span>
        <h1>Simple paths from first workspace to production gates.</h1>
        <p>
          Start with the dashboard. Add team workflows, replay proof, goldens, and enterprise controls as the reliability
          loop becomes part of your release process.
        </p>
      </section>

      <section className="public-section public-plan-grid">
        {plans.map((plan) => {
          const Icon = plan.icon;
          return (
            <article key={plan.name}>
              <Icon aria-hidden="true" />
              <h2>{plan.name}</h2>
              <strong>{plan.price}</strong>
              <p>{plan.body}</p>
              <div>
                {plan.bullets.map((bullet) => (
                  <span key={bullet}>
                    <CheckCircle2 aria-hidden="true" />
                    {bullet}
                  </span>
                ))}
              </div>
              <Link href="/auth/register" className="public-primary-button">
                Get Started
                <ArrowRight aria-hidden="true" />
              </Link>
            </article>
          );
        })}
      </section>

      <PublicFooter />
    </main>
  );
}
