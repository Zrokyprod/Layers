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
        <span className="nbell-icon" aria-hidden="true">🔔</span>
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
                ✓ Mark all read
              </button>
            )}
          </div>

          <div className="nbell-list">
            {loading && <div className="empty">Loading…</div>}
            {!loading && items.length === 0 && <div className="empty">No notifications</div>}
            {items.map((n) => (
              <div key={n.notification_id} className={`nbell-item${n.is_read ? " nbell-item-read" : " nbell-item-unread"}`}>
                <div className="nbell-item-body">
                  <p className="nbell-item-title">{n.title}</p>
                  {n.body && <p className="nbell-item-text">{n.body}</p>}
                  <p className="nbell-item-time">{new Date(n.created_at).toLocaleString()}</p>
                  {n.action_url && (
                    <Link href={n.action_url} className="nbell-item-link" onClick={() => setOpen(false)}>
                      View →
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
                      ✓
                    </button>
                  )}
                  <button
                    type="button"
                    className="nbell-icon-btn nbell-icon-btn-del"
                    onClick={() => void onDelete(n.notification_id)}
                    aria-label="Delete"
                    title="Delete"
                  >
                    ✕
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
      .catch(() => {
        // Silently ignore; auth or backend may not be ready
      })
      .finally(() => setLoading(false));
  }, [open]);

  // Poll unread count every 30s when closed
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
    setItems((prev) => prev.filter((n) => n.notification_id !== id));
    const removed = items.find((n) => n.notification_id === id);
    if (removed && !removed.is_read) {
      setUnreadCount((c) => Math.max(0, c - 1));
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="relative rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border bg-popover shadow-lg">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                onClick={onMarkAllRead}
              >
                <Check className="h-3 w-3" />
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-auto">
            {loading && (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">Loading...</div>
            )}
            {!loading && items.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">No notifications</div>
            )}
            {items.map((n) => (
              <div
                key={n.notification_id}
                className={`flex items-start gap-2 border-b px-4 py-3 last:border-0 ${
                  n.is_read ? "opacity-70" : "bg-accent/40"
                }`}
              >
                <div className="flex-1">
                  <p className="text-sm font-medium">{n.title}</p>
                  {n.body && <p className="text-xs text-muted-foreground">{n.body}</p>}
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    {new Date(n.created_at).toLocaleString()}
                  </p>
                  {n.action_url && (
                    <Link href={n.action_url} className="text-xs text-primary hover:underline" onClick={() => setOpen(false)}>
                      View
                    </Link>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  {!n.is_read && (
                    <button
                      type="button"
                      className="rounded p-1 hover:bg-accent"
                      onClick={() => onMarkRead(n.notification_id)}
                      aria-label="Mark as read"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded p-1 hover:bg-accent"
                    onClick={() => onDelete(n.notification_id)}
                    aria-label="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="border-t px-4 py-2 text-center">
            <Link href="/notifications" className="text-xs text-primary hover:underline" onClick={() => setOpen(false)}>
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
