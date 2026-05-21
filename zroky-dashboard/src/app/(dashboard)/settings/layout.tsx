"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Settings tabs per ZROKY-TECHNICAL-PLAN-V2.md §10.5 (Settings spec).
// Support tab removed in Module 1 — support routes via founder console (Module 11).
const SETTINGS_TABS = [
  { href: "/settings", label: "Project", exact: true },
  { href: "/settings/keys", label: "API Keys" },
  { href: "/settings/providers", label: "Providers" },
  { href: "/settings/team", label: "Members" },
  { href: "/settings/billing", label: "Plan & Billing" },
  { href: "/settings/profile", label: "Profile" },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  function isActive(href: string, exact?: boolean): boolean {
    return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
  }

  return (
    <div>
      <nav aria-label="Settings sections" className="settings-tabs-nav">
        {SETTINGS_TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`settings-tab-link${isActive(tab.href, "exact" in tab ? tab.exact : undefined) ? " settings-tab-link-active" : ""}`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
