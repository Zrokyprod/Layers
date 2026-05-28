import Link from "next/link";
import { ArrowRight } from "lucide-react";

const navLinks = [
  { label: "Dashboard", href: "/#dashboard" },
  { label: "Details", href: "/details" },
  { label: "Blog", href: "/blog" },
  { label: "Pricing", href: "/pricing" },
];

const footerGroups = [
  {
    title: "Product",
    links: [
      { label: "Dashboard", href: "/#dashboard" },
      { label: "Details", href: "/details" },
      { label: "Pricing", href: "/pricing" },
      { label: "Get started", href: "/auth/register" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "Blog", href: "/blog" },
      { label: "Release loop", href: "/details#release-loop" },
      { label: "Reliability guide", href: "/blog#guide" },
      { label: "Sign in", href: "/auth/login" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Contact", href: "mailto:sales@zroky.ai" },
      { label: "Security", href: "/details#security" },
      { label: "Status", href: "/#status" },
      { label: "Roadmap", href: "/blog#roadmap" },
    ],
  },
];

export function PublicNav() {
  return (
    <header className="public-nav">
      <Link href="/" className="public-brand" aria-label="Zroky home">
        <span className="public-brand-mark" aria-hidden="true">Z</span>
        <span>Zroky</span>
      </Link>

      <nav className="public-nav-links" aria-label="Public navigation">
        {navLinks.map((link) => (
          <Link key={link.href} href={link.href}>
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="public-nav-actions">
        <Link href="/auth/login" className="public-link-button">
          Login
        </Link>
        <Link href="/auth/register" className="public-primary-button">
          Get Started
          <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-top">
        <div>
          <Link href="/" className="public-brand public-footer-brand" aria-label="Zroky home">
            <span className="public-brand-mark" aria-hidden="true">Z</span>
            <span>Zroky</span>
          </Link>
          <p>
            The operating dashboard for AI agent reliability: incidents, evidence, replay proof, drift, cost, and release gates in one workflow.
          </p>
        </div>

        <div className="public-footer-grid">
          {footerGroups.map((group) => (
            <nav key={group.title} aria-label={group.title}>
              <h2>{group.title}</h2>
              {group.links.map((link) => (
                <Link key={`${group.title}-${link.href}-${link.label}`} href={link.href}>
                  {link.label}
                </Link>
              ))}
            </nav>
          ))}
        </div>
      </div>

      <div className="public-footer-bottom">
        <span>Copyright {new Date().getFullYear()} Zroky AI.</span>
        <span>Production reliability for AI agents.</span>
      </div>
    </footer>
  );
}
