"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  deleteNotification,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { NotificationItem } from "@/lib/types";

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listNotifications({ unread_only: filter === "unread", limit: 100, offset: 0 });
      setItems(data.items);
      setUnreadCount(data.unread_count);
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg ?? "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  async function onMarkRead(id: string) {
    try {
      await markNotificationRead(id);
      setItems((prev) => prev.map((n) => n.notification_id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n));
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch { /* ignore */ }
  }

  async function onMarkAllRead() {
    try {
      await markAllNotificationsRead();
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() })));
      setUnreadCount(0);
    } catch { /* ignore */ }
  }

  async function onDelete(id: string) {
    try {
      await deleteNotification(id);
      const removed = items.find((n) => n.notification_id === id);
      setItems((prev) => prev.filter((n) => n.notification_id !== id));
      if (removed && !removed.is_read) setUnreadCount((c) => Math.max(0, c - 1));
    } catch { /* ignore */ }
  }

  const displayed = useMemo(
    () => (filter === "unread" ? items.filter((n) => !n.is_read) : items),
    [items, filter],
  );

  return (
    <>
      {/* ── KPI strip ── */}
      <div className="kpi-grid loop-kpi-grid">
        <article className={`kpi-card${unreadCount > 0 ? " kpi-card-danger" : ""}`}>
          <span className="kpi-label">Unread</span>
          <strong className={`kpi-value${unreadCount > 0 ? " kpi-value-danger" : ""}`}>{unreadCount}</strong>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Total</span>
          <strong className="kpi-value">{items.length}</strong>
        </article>
      </div>

      {/* ── Notification list ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Notifications</h3>
            <p>{displayed.length} shown</p>
          </div>
          <div className="notif-toolbar">
            <select
              className="input notif-filter-select"
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | "unread")}
            >
              <option value="all">All</option>
              <option value="unread">Unread only</option>
            </select>
            <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
              Refresh
            </button>
            {unreadCount > 0 && (
              <button type="button" className="btn btn-soft" onClick={() => void onMarkAllRead()}>
                Mark all read
              </button>
            )}
          </div>
        </header>

        {error && <p className="notif-error">{error}</p>}

        {loading && displayed.length === 0 ? (
          <div className="loading" />
        ) : displayed.length === 0 ? (
          <div className="empty">
            {filter === "unread" ? "No unread notifications." : "No notifications found."}
          </div>
        ) : (
          <div className="list">
            {displayed.map((n) => (
              <div key={n.notification_id} className={`notif-row${n.is_read ? " notif-read" : " notif-unread"}`}>
                <div className="notif-body">
                  <div className="notif-title-row">
                    {!n.is_read && <span className="notif-dot" aria-hidden="true" />}
                    <strong>{n.title}</strong>
                    <span className="alert-cat-badge">{n.category}</span>
                  </div>
                  {n.body && <p className="notif-body-text">{n.body}</p>}
                  <div className="notif-meta">
                    <span className="mono">{formatDateTime(n.created_at)}</span>
                    {n.action_url && (
                      <Link href={n.action_url} className="notif-action-link">
                        View details →
                      </Link>
                    )}
                  </div>
                </div>
                <div className="notif-actions">
                  {!n.is_read && (
                    <button
                      type="button"
                      className="btn btn-soft btn-sm"
                      onClick={() => void onMarkRead(n.notification_id)}
                      title="Mark as read"
                    >
                      ✓
                    </button>
                  )}
                  <button
                    type="button"
                    className="notif-delete-btn"
                    onClick={() => void onDelete(n.notification_id)}
                    title="Delete"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
