"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  CreditCard,
  FolderOpen,
  KeyRound,
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
  { href: "/settings/billing", label: "Plan & Billing", description: "Plan and usage", icon: CreditCard },
  { href: "/settings/workspace", label: "Workspace", description: "Project metadata", icon: FolderOpen },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="settings-shell">
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
