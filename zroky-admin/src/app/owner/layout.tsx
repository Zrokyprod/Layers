"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  BadgeDollarSign,
  GitBranch,
  Home,
  KeyRound,
  LogOut,
  MessageSquare,
  ServerCog,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  clearOwnerToken,
  verifyOwnerSession,
  verifyOwnerToken,
} from "@/lib/owner-api";

type OwnerNavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
  visibleInNav?: boolean;
};

const NAV_GROUPS: ReadonlyArray<{ label: string; items: ReadonlyArray<OwnerNavItem> }> = [
  {
    label: "Operate",
    items: [
      { href: "/owner", label: "Overview", icon: Home, description: "Live paid traffic, customer actions, money, and infra" },
      { href: "/owner/money-path", label: "Money Path", icon: GitBranch, description: "Customer payment, entitlements, proof, and owner actions" },
      { href: "/owner/infrastructure", label: "Infrastructure", icon: ServerCog, description: "API, DB, Redis, gateway, workers, and smoke checks" },
    ],
  },
  {
    label: "Customers",
    items: [
      { href: "/owner/projects", label: "Tenants", icon: Activity, description: "Customers, plan, protected actions, proof quota, and next action" },
      { href: "/owner/users", label: "Users", icon: Users, description: "Accounts, access, and subscription changes" },
      { href: "/owner/pricing", label: "Billing", icon: BadgeDollarSign, description: "Accounts, recovery, plan and pricing" },
      { href: "/owner/support", label: "Support", icon: MessageSquare, description: "Tickets and urgent customer issues" },
    ],
  },
  {
    label: "Platform",
    items: [
      { href: "/owner/tool-catalog", label: "Connector Catalog", icon: SlidersHorizontal, description: "Source-of-record connectors and custom fallback" },
      { href: "/owner/audit", label: "Audit", icon: ShieldCheck, description: "Owner actions, plan grants, deletes" },
      { href: "/owner/settings", label: "Settings", icon: Settings, description: "Session, guardrails, platform rate limits" },
    ],
  },
];

const VISIBLE_NAV_GROUPS = NAV_GROUPS.map((group) => ({
  ...group,
  items: group.items.filter((item) => item.visibleInNav !== false),
})).filter((group) => group.items.length > 0);

const OWNER_SCOPE_LABEL = process.env.NODE_ENV === "production" ? "Production scoped" : "Local dev";
const OWNER_SCOPE_CLASS = process.env.NODE_ENV === "production" ? "owner-env-pill-prod" : "owner-env-pill-local";

function isActive(pathname: string, href: string): boolean {
  return href === "/owner" ? pathname === "/owner" : pathname.startsWith(href);
}

function currentPage(pathname: string): OwnerNavItem {
  return (
    NAV_GROUPS.flatMap((group) => group.items).find((item) => isActive(pathname, item.href)) ??
    NAV_GROUPS[0].items[0]
  );
}

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [authed, setAuthed] = useState<boolean | null>(null); // null = checking
  const [tokenInput, setTokenInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Check if stored token is still valid on mount
  useEffect(() => {
    verifyOwnerSession().then((ok) => setAuthed(ok));
  }, []);

  const handleLogin = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      const ok = await verifyOwnerToken(tokenInput.trim());
      if (ok) {
        setAuthed(true);
        setTokenInput("");
      } else {
        setError("Invalid token. Check your PROVISIONING_TOKEN.");
      }
      setLoading(false);
    },
    [tokenInput],
  );

  const handleLogout = useCallback(() => {
    clearOwnerToken();
    setAuthed(false);
    setTokenInput("");
  }, []);

  // Loading state.
  if (authed === null) {
    return (
      <div className="owner-checking">
        <p className="hint">Checking access...</p>
      </div>
    );
  }

  // Token gate.
  if (!authed) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="owner-gate-header">
            <div className="owner-gate-logo">Z</div>
            <h1 className="auth-heading">Owner Dashboard</h1>
            <p className="auth-sub">Enter your provisioning token to open the owner control plane</p>
          </div>
          <form onSubmit={handleLogin} className="auth-form">
            <div className="field">
              <label htmlFor="owner-token" className="field-label">Provisioning Token</label>
              <input
                id="owner-token"
                type="password"
                placeholder="your-provisioning-token"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                required
                autoFocus
              />
            </div>
            {error && <p className="field-error">{error}</p>}
            <button
              type="submit"
              className="btn btn-primary auth-submit-btn"
              disabled={loading || !tokenInput.trim()}
            >
              {loading ? "Verifying..." : "Enter Dashboard"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Authenticated shell.
  return (
    <div className="owner-shell">
      <aside className="owner-sidebar" aria-label="Owner navigation">
        <div className="owner-topbar-brand owner-sidebar-brand">
          <div className="owner-logo">Z</div>
          <div>
            <span className="owner-brand-name">Zroky Owner</span>
            <span className="owner-brand-sub">Owner control plane</span>
          </div>
        </div>

        <nav className="owner-nav">
          {VISIBLE_NAV_GROUPS.map((group) => (
            <div key={group.label} className="owner-nav-group">
              <span className="owner-nav-group-label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`owner-nav-link${active ? " owner-nav-link-active" : ""}`}
                    title={item.description}
                  >
                    <Icon className="owner-nav-icon" aria-hidden="true" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="owner-sidebar-foot">
          <div className="owner-profile-card">
            <div className="owner-profile-avatar">
              <KeyRound size={15} aria-hidden="true" />
            </div>
            <div>
              <strong>Owner session</strong>
              <span>Provisioning-token access</span>
            </div>
          </div>
          <button className="owner-signout-btn" onClick={handleLogout}>
            <LogOut size={15} aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <section className="owner-main">
        <header className="owner-topbar">
          <div>
            <p className="owner-topbar-kicker">Zroky Owner</p>
            <h1>{currentPage(pathname).label}</h1>
            <p>{currentPage(pathname).description}</p>
          </div>
          <div className="owner-topbar-status">
            <span className="owner-env-pill">Admin</span>
            <span className={`owner-env-pill ${OWNER_SCOPE_CLASS}`}>{OWNER_SCOPE_LABEL}</span>
          </div>
        </header>

        <main className="owner-content">{children}</main>
      </section>
    </div>
  );
}
