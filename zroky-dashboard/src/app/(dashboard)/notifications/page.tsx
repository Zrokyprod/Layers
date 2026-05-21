"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { deleteNotification, listNotifications, markAllNotificationsRead, markNotificationRead } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";
import { useDashboardStore } from "@/lib/store";

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const setUnreadNotifications = useDashboardStore((state) => state.setUnreadNotifications);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const payload = await listNotifications({ unread_only: unreadOnly, limit: 100 });
      setItems(payload.items);
      setTotal(payload.total);
      setUnreadNotifications(payload.unread_count);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [setUnreadNotifications, unreadOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  async function markOneRead(item: NotificationItem) {
    if (item.is_read) return;
    await markNotificationRead(item.notification_id);
    await load();
  }

  async function markAllRead() {
    const result = await markAllNotificationsRead();
    setMessage(`${result.marked_count} notifications marked read.`);
    await load();
  }

  async function removeNotification(item: NotificationItem) {
    await deleteNotification(item.notification_id);
    setMessage("Notification deleted.");
    await load();
  }

  return (
    <div className="page-stack notifications-page">
      <section className="panel settings-hero-panel">
        <div>
          <p className="eyebrow">Inbox</p>
          <h2>Notifications</h2>
          <p className="hint">Review alerts, product updates, owner broadcasts, and reliability events for your account.</p>
        </div>
        <div className="actions">
          <button className="btn btn-soft" type="button" onClick={() => setUnreadOnly((value) => !value)}>
            {unreadOnly ? "Show all" : "Unread only"}
          </button>
          <button className="btn btn-primary" type="button" onClick={() => void markAllRead()} disabled={items.length === 0}>
            Mark all read
          </button>
        </div>
      </section>

      {message ? <div className="alert-strip">{message}</div> : null}

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>{unreadOnly ? "Unread notifications" : "All notifications"}</h3>
            <p>{total.toLocaleString()} total notifications</p>
          </div>
          <button className="btn btn-soft" type="button" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </header>

        {loading ? <p className="hint">Loading notifications…</p> : null}
        {!loading && items.length === 0 ? <p className="hint">No notifications found.</p> : null}

        <div className="notification-page-list">
          {items.map((item) => (
            <article key={item.notification_id} className={item.is_read ? "notification-card notification-card-read" : "notification-card"}>
              <div className="notification-card-main">
                <div>
                  <div className="notification-card-title-row">
                    <h3>{item.title}</h3>
                    {!item.is_read ? <span className="pill pill-success">Unread</span> : <span className="pill">Read</span>}
                  </div>
                  {item.body ? <p>{item.body}</p> : null}
                  <div className="notification-card-meta">
                    <span>{item.category}</span>
                    <span>{formatDate(item.created_at)}</span>
                  </div>
                </div>
              </div>
              <div className="notification-card-actions">
                {item.action_url ? <Link className="btn btn-soft" href={item.action_url} onClick={() => void markOneRead(item)}>Open</Link> : null}
                {!item.is_read ? (
                  <button className="btn btn-soft" type="button" onClick={() => void markOneRead(item)}>
                    Mark read
                  </button>
                ) : null}
                <button className="btn btn-danger" type="button" onClick={() => void removeNotification(item)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
