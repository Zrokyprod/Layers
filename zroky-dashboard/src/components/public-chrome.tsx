import Link from "next/link";
import { ArrowRight } from "lucide-react";

const navLinks = [
  { label: "Product", href: "/#product" },
  { label: "Proof Loop", href: "/#proof-loop" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Docs", href: "/#quickstart" },
];

const footerGroups = [
  {
    title: "Product",
    links: [
      { label: "Product", href: "/product" },
      { label: "Pricing", href: "/#pricing" },
      { label: "Docs", href: "/#quickstart" },
      { label: "Start free", href: "/signup" },
    ],
  },
  {
    title: "Reliability",
    links: [
      { label: "Capture", href: "/#proof-loop" },
      { label: "Replay Lab", href: "/#proof-loop" },
      { label: "Golden traces", href: "/#proof-loop" },
      { label: "CI gates", href: "/#proof-loop" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Docs", href: "/#quickstart" },
      { label: "Contact", href: "mailto:sales@zroky.com" },
      { label: "Sign in", href: "/login" },
    ],
  },
];

export function PublicNav() {
  return (
    <header className="z-nav">
      <Link href="/" className="z-brand" aria-label="Zroky home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/zroky-auth-logo.png" alt="Zroky" />
      </Link>

      <nav className="z-nav-links" aria-label="Public navigation">
        {navLinks.map((link) => (
          <Link key={link.href} href={link.href}>
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="z-nav-actions">
        <Link href="/login" className="z-link-button">
          Sign in
        </Link>
        <Link href="/signup" className="z-primary-button">
          Start free
          <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="z-footer">
      <div className="z-footer-top">
        <div className="z-footer-brand-block">
          <Link href="/" className="z-brand z-footer-brand" aria-label="Zroky home">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/zroky-auth-logo.png" alt="Zroky" />
          </Link>
          <p>
            Zroky captures failed AI-agent runs, diagnoses root cause, replays the exact scenario, and turns verified
            fixes into release gates.
          </p>
        </div>

        <div className="z-footer-grid">
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

      <div className="z-footer-bottom">
        <span>Copyright {new Date().getFullYear()} Zroky AI.</span>
        <span>No fake logos. No fake testimonials. Built around production reliability proof.</span>
      </div>
    </footer>
  );
}
