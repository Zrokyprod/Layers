"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell } from "lucide-react";

import { listNotifications, markAllNotificationsRead, markNotificationRead } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";
import { useDashboardStore } from "@/lib/store";

function formatRelative(value: string) {
  const timestamp = new Date(value).getTime();
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (deltaSeconds < 60) return "now";
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)}h ago`;
  return `${Math.floor(deltaSeconds / 86400)}d ago`;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const unreadNotifications = useDashboardStore((state) => state.unreadNotifications);
  const setUnreadNotifications = useDashboardStore((state) => state.setUnreadNotifications);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await listNotifications({ limit: 5 });
      setItems(payload.items);
      setUnreadNotifications(payload.unread_count);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [setUnreadNotifications]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  const unreadItems = useMemo(() => items.filter((item) => !item.is_read), [items]);

  async function markOneRead(item: NotificationItem) {
    if (item.is_read) return;
    await markNotificationRead(item.notification_id);
    setItems((prev) => prev.map((entry) => entry.notification_id === item.notification_id ? { ...entry, is_read: true, read_at: new Date().toISOString() } : entry));
    setUnreadNotifications(Math.max(0, unreadNotifications - 1));
  }

  async function markAllRead() {
    await markAllNotificationsRead();
    setItems((prev) => prev.map((item) => ({ ...item, is_read: true, read_at: item.read_at ?? new Date().toISOString() })));
    setUnreadNotifications(0);
  }

  return (
    <div className="notification-bell-wrap">
      <button
        type="button"
        className="notification-bell-btn"
        aria-label={`Notifications${unreadNotifications ? `, ${unreadNotifications} unread` : ""}`}
        onClick={() => {
          setOpen((value) => !value);
          if (!open) void load();
        }}
      >
        <Bell className="notification-bell-icon" aria-hidden="true" />
        {unreadNotifications > 0 ? <span className="notification-bell-count">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span> : null}
      </button>

      {open ? (
        <div className="notification-popover">
          <div className="notification-popover-head">
            <div>
              <strong>Notifications</strong>
              <span>{unreadItems.length} unread in latest batch</span>
            </div>
            <button type="button" className="link-button" onClick={() => void markAllRead()} disabled={unreadNotifications === 0}>
              Mark all read
            </button>
          </div>

          {loading ? <p className="hint notification-empty">Loading…</p> : null}
          {error ? <p className="hint notification-error">{error}</p> : null}
          {!loading && !error && items.length === 0 ? <p className="hint notification-empty">No notifications yet.</p> : null}

          <div className="notification-list-mini">
            {items.map((item) => (
              <Link
                key={item.notification_id}
                className={item.is_read ? "notification-mini notification-mini-read" : "notification-mini"}
                href={item.action_url || "/notifications"}
                onClick={() => void markOneRead(item)}
              >
                <div>
                  <strong>{item.title}</strong>
                  {item.body ? <span>{item.body}</span> : null}
                </div>
                <small>{formatRelative(item.created_at)}</small>
              </Link>
            ))}
          </div>

          <Link className="notification-view-all" href="/notifications" onClick={() => setOpen(false)}>
            View all notifications
          </Link>
        </div>
      ) : null}
    </div>
  );
}
