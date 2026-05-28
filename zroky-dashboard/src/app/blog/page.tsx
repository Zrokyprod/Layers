import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenText, CircleDollarSign, FileCheck2, Radar } from "lucide-react";
import { PublicFooter, PublicNav } from "@/components/public-chrome";

export const metadata: Metadata = {
  title: "Blog",
  description: "Zroky notes on AI agent reliability, replay proof, drift, cost, and release gates.",
};

const posts = [
  {
    id: "guide",
    title: "The AI agent reliability loop",
    category: "Guide",
    body: "How capture, issue grouping, replay proof, and goldens turn production failures into release confidence.",
    icon: BookOpenText,
  },
  {
    id: "replay-proof",
    title: "Replay proof is not the same as a passing unit test",
    category: "Replay",
    body: "Why teams need real incident comparison before calling an agent behavior fix verified.",
    icon: FileCheck2,
  },
  {
    id: "drift",
    title: "Provider drift needs an owner",
    category: "Drift",
    body: "A dashboard view for latency, output, judge, and model changes that can quietly break workflows.",
    icon: Radar,
  },
  {
    id: "roadmap",
    title: "Cost of failure belongs beside issue severity",
    category: "Roadmap",
    body: "Repeated retries, failed loops, and weak evidence can be measured as direct operational waste.",
    icon: CircleDollarSign,
  },
];

export default function BlogPage() {
  return (
    <main className="public-site public-subpage">
      <PublicNav />

      <section className="public-subpage-hero">
        <span className="public-kicker">Blog</span>
        <h1>Notes from the agent reliability desk.</h1>
        <p>
          Practical writing for teams building production agents: diagnosis, replay proof, drift, cost, and release gates.
        </p>
      </section>

      <section className="public-section public-blog-grid">
        {posts.map((post) => {
          const Icon = post.icon;
          return (
            <article key={post.id} id={post.id}>
              <span className="public-blog-category">{post.category}</span>
              <Icon aria-hidden="true" />
              <h2>{post.title}</h2>
              <p>{post.body}</p>
              <Link href="/auth/register">
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
