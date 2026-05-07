"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  deleteNotification,
} from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    listNotifications({ limit: 20 })
      .then((data) => {
        setItems(data.items);
        setUnreadCount(data.unread_count);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (open) return;
    const id = setInterval(() => {
      listNotifications({ unread_only: true, limit: 1 })
        .then((data) => setUnreadCount(data.unread_count))
        .catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, [open]);

  async function onMarkRead(id: string) {
    await markNotificationRead(id);
    setItems((prev) =>
      prev.map((n) => (n.notification_id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
    );
    setUnreadCount((c) => Math.max(0, c - 1));
  }

  async function onMarkAllRead() {
    await markAllNotificationsRead();
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() })));
    setUnreadCount(0);
  }

  async function onDelete(id: string) {
    await deleteNotification(id);
    const removed = items.find((n) => n.notification_id === id);
    setItems((prev) => prev.filter((n) => n.notification_id !== id));
    if (removed && !removed.is_read) {
      setUnreadCount((c) => Math.max(0, c - 1));
    }
  }

  return (
    <div className="nbell-root" ref={ref}>
      <button
        type="button"
        className="nbell-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
      >
        <span className="nbell-icon" aria-hidden="true">≡ƒöö</span>
        {unreadCount > 0 && (
          <span className="nbell-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>

      {open && (
        <div className="nbell-dropdown">
          <div className="nbell-header">
            <span className="nbell-title">Notifications</span>
            {unreadCount > 0 && (
              <button type="button" className="nbell-mark-all" onClick={() => void onMarkAllRead()}>
                Γ£ô Mark all read
              </button>
            )}
          </div>

          <div className="nbell-list">
            {loading && <div className="empty">LoadingΓÇª</div>}
            {!loading && items.length === 0 && <div className="empty">No notifications</div>}
            {items.map((n) => (
              <div key={n.notification_id} className={`nbell-item${n.is_read ? " nbell-item-read" : " nbell-item-unread"}`}>
                <div className="nbell-item-body">
                  <p className="nbell-item-title">{n.title}</p>
                  {n.body && <p className="nbell-item-text">{n.body}</p>}
                  <p className="nbell-item-time">{new Date(n.created_at).toLocaleString()}</p>
                  {n.action_url && (
                    <Link href={n.action_url} className="nbell-item-link" onClick={() => setOpen(false)}>
                      View ΓåÆ
                    </Link>
                  )}
                </div>
                <div className="nbell-item-actions">
                  {!n.is_read && (
                    <button
                      type="button"
                      className="nbell-icon-btn"
                      onClick={() => void onMarkRead(n.notification_id)}
                      aria-label="Mark as read"
                      title="Mark as read"
                    >
                      Γ£ô
                    </button>
                  )}
                  <button
                    type="button"
                    className="nbell-icon-btn nbell-icon-btn-del"
                    onClick={() => void onDelete(n.notification_id)}
                    aria-label="Delete"
                    title="Delete"
                  >
                    Γ£ò
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="nbell-footer">
            <Link href="/notifications" className="nbell-view-all" onClick={() => setOpen(false)}>
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
