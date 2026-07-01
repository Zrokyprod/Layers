"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  ArrowRight,
  CreditCard,
  FolderOpen,
  KeyRound,
  Plug,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

type SettingsTab = {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  exact?: boolean;
};

const SETTINGS_PRIMARY_TABS: ReadonlyArray<SettingsTab> = [
  { href: "/settings/keys", label: "API Keys", description: "SDK and Gateway access", icon: KeyRound },
  { href: "/settings/team", label: "Members", description: "Project access", icon: Users },
  { href: "/settings/billing", label: "Plan & Billing", description: "Plan, usage, and budget", icon: CreditCard },
  { href: "/settings/workspace", label: "Workspace", description: "Project metadata", icon: FolderOpen },
] as const;

const HIDDEN_SETTINGS_TABS: ReadonlyArray<SettingsTab> = [
  { href: "/settings/integrations", label: "Connectors", description: "Moved to Connectors", icon: Plug, exact: false },
  { href: "/settings/profile", label: "Account", description: "Moved to Account", icon: Users, exact: false },
] as const;

const SETTINGS_CONTROL_LOOP: ReadonlyArray<{
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  { href: "/settings/keys", label: "API access", description: "SDK and Gateway keys", icon: KeyRound },
  { href: "/settings/team", label: "Team access", description: "Members and owner guard", icon: Users },
  { href: "/settings/billing", label: "Spend guard", description: "Plan, usage, and budget", icon: CreditCard },
  { href: "/settings/workspace", label: "Workspace record", description: "Project identity and status", icon: FolderOpen },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab =
    [...SETTINGS_PRIMARY_TABS, ...HIDDEN_SETTINGS_TABS].find((tab) =>
      isActivePath(pathname, tab.href, tab.exact)
    ) ?? SETTINGS_PRIMARY_TABS[0];
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
            <h1>Workspace control plane</h1>
            <p>Manage API access, members, billing, and workspace identity for the control plane.</p>
            <div className="settings-hero-rail" aria-label="Workspace control loop">
              {SETTINGS_CONTROL_LOOP.map((item) => {
                const RailIcon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`settings-hero-rail-link${isActivePath(pathname, item.href) ? " is-active" : ""}`}
                  >
                    <RailIcon aria-hidden="true" />
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                    <ArrowRight aria-hidden="true" className="settings-hero-rail-arrow" />
                  </Link>
                );
              })}
            </div>
          </div>
          <div className="settings-hero-current">
            <ActiveIcon aria-hidden="true" />
            <span>
              <strong>{activeTab.label}</strong>
              <small>{activeTab.description}</small>
            </span>
            <small className="settings-hero-current-caption">Current section</small>
          </div>
        </div>
      </section>

      <nav aria-label="Settings sections" className="settings-tabs-nav">
        {SETTINGS_PRIMARY_TABS.map((tab) => {
          const TabIcon = tab.icon;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`settings-tab-link${isActivePath(pathname, tab.href, tab.exact) ? " settings-tab-link-active" : ""}`}
              aria-label={tab.label}
              aria-current={isActivePath(pathname, tab.href, tab.exact) ? "page" : undefined}
            >
              <TabIcon aria-hidden="true" />
              <span>
                <strong>{tab.label}</strong>
                <small>{tab.description}</small>
              </span>
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
