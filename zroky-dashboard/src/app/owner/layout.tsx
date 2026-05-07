"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  clearOwnerToken,
  getOwnerToken,
  setOwnerToken,
  verifyOwnerToken,
} from "@/lib/owner-api";

const NAV = [
  { href: "/owner", label: "Overview" },
  { href: "/owner/infrastructure", label: "Infrastructure" },
  { href: "/owner/users", label: "Users" },
  { href: "/owner/projects", label: "Projects" },
  { href: "/owner/pricing", label: "Pricing" },
  { href: "/owner/rate-limits", label: "Rate Limits" },
  { href: "/owner/audit", label: "Audit Log" },
  { href: "/owner/platform-llm", label: "LLM Usage" },
  { href: "/owner/feature-flags", label: "Feature Flags" },
];

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [authed, setAuthed] = useState<boolean | null>(null); // null = checking
  const [tokenInput, setTokenInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Check if stored token is still valid on mount
  useEffect(() => {
    const stored = getOwnerToken();
    if (!stored) {
      setAuthed(false);
      return;
    }
    verifyOwnerToken(stored).then((ok) => setAuthed(ok));
  }, []);

  const handleLogin = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      const ok = await verifyOwnerToken(tokenInput.trim());
      if (ok) {
        setOwnerToken(tokenInput.trim());
        setAuthed(true);
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

  // ── Loading ────────────────────────────────────────────────────────────────
  if (authed === null) {
    return (
      <div className="owner-checking">
        <p className="hint">Checking access…</p>
      </div>
    );
  }

  // ── Token Gate ─────────────────────────────────────────────────────────────
  if (!authed) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="owner-gate-header">
            <div className="owner-gate-logo">Z</div>
            <h1 className="auth-heading">Owner Dashboard</h1>
            <p className="auth-sub">Enter your provisioning token to continue</p>
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
              {loading ? "Verifying…" : "Enter Dashboard"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Authenticated Shell ────────────────────────────────────────────────────
  return (
    <div className="owner-shell">
      <header className="owner-topbar">
        <div className="owner-topbar-brand">
          <div className="owner-logo">Z</div>
          <span className="owner-brand-name">Zroky Owner</span>
        </div>

        <nav className="owner-nav">
          {NAV.map((n) => {
            const active = n.href === "/owner" ? pathname === "/owner" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`owner-nav-link${active ? " owner-nav-link-active" : ""}`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>

        <button className="btn btn-soft owner-signout-btn" onClick={handleLogout}>
          Sign out
        </button>
      </header>

      <main className="owner-content">
        {children}
      </main>
    </div>
  );
}
