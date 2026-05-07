"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useOwnerProjects } from "@/lib/hooks";

export default function OwnerProjectsPage() {
  const { data, isLoading, error } = useOwnerProjects(200, 0);
  const [search, setSearch] = useState("");

  const projects = data?.projects ?? [];
  const total = data?.total ?? 0;
  const loading = isLoading;
  const errorMessage = error?.message ?? "";

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return projects.filter((p) => {
      return !q || p.name.toLowerCase().includes(q) || (p.owner_ref ?? "").toLowerCase().includes(q) || p.id.includes(q);
    });
  }, [projects, search]);

  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });

  const usd = (n: number) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(n);

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">All Projects</h2>
          <p className="hint">{total} projects across all users</p>
        </div>
        <input
          className="input"
          placeholder="Search by name or owner…"
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
                {["Project", "Owner", "Calls", "Total Cost", "Status", "Created", ""].map((h) => (
                  <th key={h} className="owner-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="owner-td owner-td-empty">No projects found</td>
                </tr>
              )}
              {filtered.map((p, i) => (
                <tr key={p.id} className={`owner-tr${i < filtered.length - 1 ? "" : " owner-tr-last"}`}>
                  <td className="owner-td">
                    <div className="owner-user-name">{p.name}</div>
                    <div className="owner-user-id">{p.id}</div>
                  </td>
                  <td className="owner-td owner-td-secondary">{p.owner_ref ?? "—"}</td>
                  <td className="owner-td">{p.call_count.toLocaleString()}</td>
                  <td className="owner-td">{usd(p.total_cost_usd)}</td>
                  <td className="owner-td">
                    {p.is_active ? <span className="pill pill-green">Active</span> : <span className="pill pill-red">Inactive</span>}
                  </td>
                  <td className="owner-td">{fmt(p.created_at)}</td>
                  <td className="owner-td">
                    <Link href={`/owner/projects/${p.id}`} className="owner-row-link">View →</Link>
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
