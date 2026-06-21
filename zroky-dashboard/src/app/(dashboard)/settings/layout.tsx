"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  CreditCard,
  BellRing,
  KeyRound,
  Plug,
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
  { href: "/settings/keys", label: "API keys", description: "Capture credentials", icon: KeyRound },
  { href: "/settings/team", label: "Members", description: "Project access", icon: Users },
  { href: "/settings/billing", label: "Plan & Billing", description: "Plan, usage, and budget", icon: CreditCard },
  { href: "/settings/evaluation", label: "Evaluation", description: "Judge calibration", icon: SlidersHorizontal },
  { href: "/settings/integrations", label: "Integrations", description: "Repos, alerts, records", icon: BellRing },
] as const;

const HIDDEN_SETTINGS_TABS = [
  { href: "/settings/providers", label: "Providers", description: "Managed replay vault", icon: Plug, exact: false },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab =
    [...SETTINGS_TABS, ...HIDDEN_SETTINGS_TABS].find((tab) => isActivePath(pathname, tab.href, tab.exact)) ??
    SETTINGS_TABS[0];
  const ActiveIcon = activeTab.icon;

  return (
    <div className="settings-shell">
      <section className="module-hero settings-hero">
        <div className="module-hero-header">
          <div>
            <span className="module-eyebrow">
              <ShieldCheck aria-hidden="true" />
              Settings
            </span>
            <h1>Settings</h1>
            <p>Manage capture keys, members, billing, evaluation, and integrations.</p>
          </div>
          <div className="settings-hero-current">
            <ActiveIcon aria-hidden="true" />
            <span>
              <strong>{activeTab.label}</strong>
              <small>{activeTab.description}</small>
            </span>
          </div>
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
