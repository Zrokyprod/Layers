"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { useOwnerUsers } from "@/lib/hooks";

const PAGE_SIZE = 50;

export default function OwnerUsersPage() {
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [page, setPage] = useState(0);
  const offset = page * PAGE_SIZE;
  const { data, isLoading, isFetching, error } = useOwnerUsers({
    limit: PAGE_SIZE,
    offset,
    search: submittedSearch,
  });

  const users = useMemo(() => data?.users ?? [], [data?.users]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const loading = isLoading;
  const errorMessage = error?.message ?? "";

  useEffect(() => {
    setPage(0);
  }, [submittedSearch]);

  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmittedSearch(search.trim());
  }

  return (
    <div className="owner-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">All Users</h2>
          <p className="hint">
            {total} registered accounts
            {submittedSearch ? ` matching "${submittedSearch}"` : ""} - page {page + 1} of {totalPages}
          </p>
        </div>
        <form onSubmit={submitSearch} className="actions" style={{ gap: 8 }}>
          <input
            className="input"
            placeholder="Search all users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 280 }}
          />
          <button className="btn btn-primary" type="submit" disabled={isFetching}>
            Search
          </button>
          {submittedSearch ? (
            <button
              className="btn btn-soft"
              type="button"
              disabled={isFetching}
              onClick={() => {
                setSearch("");
                setSubmittedSearch("");
              }}
            >
              Clear
            </button>
          ) : null}
        </form>
      </div>

      {errorMessage && <div className="alert-strip alert-strip-error">{errorMessage}</div>}

      {loading && !errorMessage && <p className="hint">Loading users...</p>}

      {!loading && !errorMessage && (
        <>
          {isFetching ? <p className="hint">Refreshing users...</p> : null}
          <div className="owner-table-wrap">
            <table className="owner-table">
              <thead>
                <tr>
                  {["Email / Login", "Login method", "Projects", "Status", "Joined", ""].map((h) => (
                    <th key={h} className="owner-th">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="owner-td owner-td-empty">No users found</td>
                  </tr>
                )}
                {users.map((u, i) => (
                  <tr key={u.id} className={`owner-tr${i < users.length - 1 ? "" : " owner-tr-last"}`}>
                    <td className="owner-td">
                      <div className="owner-user-cell">
                        <div className="owner-avatar">
                          {(u.email ?? u.github_login ?? "?")[0].toUpperCase()}
                        </div>
                        <div>
                          <div className="owner-user-name">{u.email ?? u.github_login ?? "-"}</div>
                          <div className="owner-user-id">{u.id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="owner-td">
                      {u.github_login ? <span className="pill">GitHub</span> : u.email ? <span className="pill">Email</span> : "-"}
                    </td>
                    <td className="owner-td">{u.project_count}</td>
                    <td className="owner-td">
                      {u.is_active ? <span className="pill pill-green">Active</span> : <span className="pill pill-red">Inactive</span>}
                    </td>
                    <td className="owner-td">{fmt(u.created_at)}</td>
                    <td className="owner-td">
                      <Link href={`/owner/users/${u.id}`} className="owner-row-link">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions" style={{ justifyContent: "space-between", marginTop: 16 }}>
            <button
              className="btn btn-soft"
              type="button"
              disabled={page === 0 || isFetching}
              onClick={() => setPage((current) => Math.max(0, current - 1))}
            >
              Previous
            </button>
            <span className="hint">
              Showing {total === 0 ? 0 : offset + 1}-{Math.min(offset + users.length, total)} of {total}
            </span>
            <button
              className="btn btn-soft"
              type="button"
              disabled={page + 1 >= totalPages || isFetching}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
