"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useOwnerUsers } from "@/lib/hooks";

export default function OwnerUsersPage() {
  const { data, isLoading, error } = useOwnerUsers(200, 0);
  const [search, setSearch] = useState("");

  const users = useMemo(() => data?.users ?? [], [data?.users]);
  const total = data?.total ?? 0;
  const loading = isLoading;
  const errorMessage = error?.message ?? "";

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return users.filter((u) => {
      return (
        !q ||
        (u.email ?? "").toLowerCase().includes(q) ||
        (u.github_login ?? "").toLowerCase().includes(q) ||
        u.id.includes(q)
      );
    });
  }, [users, search]);

  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">All Users</h2>
          <p className="hint">{total} registered accounts</p>
        </div>
        <input
          className="input"
          placeholder="Search by email or GitHub login…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280 }}
        />
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}

      {loading && !errorMessage && <p className="hint">Loading…</p>}

      {!loading && !errorMessage && (
        <div className="owner-table-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {["Email / Login", "Provider", "Projects", "Status", "Joined", ""].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="owner-td owner-td-empty">No users found</td>
                </tr>
              )}
              {filtered.map((u, i) => (
                <tr key={u.id} className={`owner-tr${i < filtered.length - 1 ? "" : " owner-tr-last"}`}>
                  <td className="owner-td">
                    <div className="owner-user-cell">
                      <div className="owner-avatar">
                        {(u.email ?? u.github_login ?? "?")[0].toUpperCase()}
                      </div>
                      <div>
                        <div className="owner-user-name">{u.email ?? u.github_login ?? "—"}</div>
                        <div className="owner-user-id">{u.id}</div>
                      </div>
                    </div>
                  </td>
                  <td className="owner-td">
                    {u.github_login ? <span className="pill">GitHub</span> : u.email ? <span className="pill">Email</span> : "—"}
                  </td>
                  <td className="owner-td">{u.project_count}</td>
                  <td className="owner-td">
                    {u.is_active ? <span className="pill pill-green">Active</span> : <span className="pill pill-red">Inactive</span>}
                  </td>
                  <td className="owner-td">{fmt(u.created_at)}</td>
                  <td className="owner-td">
                    <Link href={`/owner/users/${u.id}`} className="owner-row-link">View →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
