"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  Activity,
  CreditCard,
  BellRing,
  KeyRound,
  Plug,
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";

// Settings tabs per ZROKY-TECHNICAL-PLAN-V2.md §10.5 (Settings spec).
// Support tab removed in Module 1 — support routes via founder console (Module 11).
const SETTINGS_TABS: ReadonlyArray<{
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  exact?: boolean;
}> = [
  { href: "/settings", label: "Project", description: "Project defaults and data controls", icon: SettingsIcon, exact: true },
  { href: "/settings/keys", label: "API keys", description: "Capture and ingest credentials", icon: KeyRound },
  { href: "/settings/providers", label: "Providers", description: "Model provider vault", icon: Plug },
  { href: "/settings/team", label: "Members", description: "Project access", icon: Users },
  { href: "/settings/billing", label: "Plan & Billing", description: "Subscription and usage", icon: CreditCard },
  { href: "/settings/evaluation", label: "Evaluation", description: "Judge and calibration controls", icon: SlidersHorizontal },
  { href: "/settings/integrations", label: "Integrations", description: "Slack and Teams delivery", icon: BellRing },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab = SETTINGS_TABS.find((tab) => isActivePath(pathname, tab.href, tab.exact)) ?? SETTINGS_TABS[0];
  const ActiveIcon = activeTab.icon;

  return (
    <div className="settings-shell">
      <section className="module-hero settings-hero">
        <div className="module-hero-header">
          <div>
            <span className="module-eyebrow">
              <ShieldCheck aria-hidden="true" />
              Control plane
            </span>
            <h1>Settings Control Plane</h1>
            <p>Configure the project surface that captures failures, protects secrets, gates releases, and routes alerts.</p>
          </div>
          <div className="settings-hero-current">
            <ActiveIcon aria-hidden="true" />
            <span>
              <strong>{activeTab.label}</strong>
              <small>{activeTab.description}</small>
            </span>
          </div>
        </div>
        <div className="settings-hero-rail" aria-label="Settings trust areas">
          <span><Activity aria-hidden="true" /> Live project state</span>
          <span><ShieldCheck aria-hidden="true" /> Guarded destructive actions</span>
          <span><KeyRound aria-hidden="true" /> Secret rotation controls</span>
        </div>
      </section>

      <nav aria-label="Settings sections" className="settings-tabs-nav">
        {SETTINGS_TABS.map((tab) => {
          const TabIcon = tab.icon;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`settings-tab-link${isActivePath(pathname, tab.href, tab.exact) ? " settings-tab-link-active" : ""}`}
            >
              <TabIcon aria-hidden="true" />
              {tab.label}
            </Link>
          );
        })}
      </nav>

      <div className="settings-content">{children}</div>
    </div>
  );
}

function isActivePath(pathname: string, href: string, exact?: boolean): boolean {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}
