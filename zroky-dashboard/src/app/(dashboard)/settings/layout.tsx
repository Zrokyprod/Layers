"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const SETTINGS_TABS = [
  { href: "/settings", label: "General", exact: true },
  { href: "/settings/keys", label: "API Keys" },
  { href: "/settings/providers", label: "Providers" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/team", label: "Team" },
  { href: "/settings/support", label: "Support" },
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
