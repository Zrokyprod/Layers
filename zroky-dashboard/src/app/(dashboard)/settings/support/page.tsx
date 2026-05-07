"use client";

import { useCallback, useEffect, useState } from "react";

import {
  addSupportMessage,
  createSupportTicket,
  getSupportTicket,
  listSupportTickets,
  updateSupportTicket,
} from "@/lib/api";
import type { SupportTicketItem, SupportMessageItem } from "@/lib/types";

export default function SupportPage() {
  const [tickets, setTickets] = useState<SupportTicketItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const [selectedTicket, setSelectedTicket] = useState<SupportTicketItem | null>(null);
  const [messages, setMessages] = useState<SupportMessageItem[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCategory, setNewCategory] = useState("general");
  const [createBusy, setCreateBusy] = useState(false);

  const [replyBody, setReplyBody] = useState("");
  const [replyBusy, setReplyBusy] = useState(false);

  const loadTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listSupportTickets({
        status: statusFilter || undefined,
        limit: 50,
      });
      setTickets(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load tickets.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  async function openTicket(ticket: SupportTicketItem) {
    setSelectedTicket(ticket);
    setDetailLoading(true);
    try {
      const res = await getSupportTicket(ticket.ticket_id);
      setSelectedTicket(res.ticket);
      setMessages(res.messages);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load ticket.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreateBusy(true);
    try {
      const ticket = await createSupportTicket({
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        category: newCategory,
      });
      setNewTitle("");
      setNewDescription("");
      setNewCategory("general");
      setTickets((prev) => [ticket, ...prev]);
      await openTicket(ticket);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create ticket.");
    } finally {
      setCreateBusy(false);
    }
  }

  async function onReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedTicket || !replyBody.trim()) return;
    setReplyBusy(true);
    try {
      const msg = await addSupportMessage(selectedTicket.ticket_id, { body: replyBody.trim() });
      setMessages((prev) => [...prev, msg]);
      setReplyBody("");
      setTickets((prev) =>
        prev.map((t) =>
          t.ticket_id === selectedTicket.ticket_id ? { ...t, message_count: t.message_count + 1 } : t
        )
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to send reply.");
    } finally {
      setReplyBusy(false);
    }
  }

  async function changeStatus(ticketId: string, status: string) {
    try {
      const updated = await updateSupportTicket(ticketId, { status });
      setTickets((prev) =>
        prev.map((t) => (t.ticket_id === ticketId ? { ...updated, message_count: t.message_count } : t))
      );
      if (selectedTicket?.ticket_id === ticketId) {
        setSelectedTicket((prev) => (prev ? { ...updated, message_count: prev.message_count } : prev));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update ticket.");
    }
  }

  const statusOptions = ["", "open", "in_progress", "resolved", "closed"];
  const categoryOptions = ["general", "billing", "technical", "feature_request", "bug"];

  return (
    <div className="page-content">
      {error && <div className="alert-strip alert-strip-error">{error}</div>}

      {/* New ticket form */}
      <section className="panel">
        <header className="panel-header">
          <h3>New Support Ticket</h3>
          <p>Report an issue or ask a question.</p>
        </header>
        <form onSubmit={onCreate}>
          <div className="field">
            <label className="field-label">Title</label>
            <input
              className="input"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Brief summary of your issue"
              required
            />
          </div>
          <div className="field">
            <label className="field-label">Category</label>
            <select className="input" value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
              {categoryOptions.map((c) => (
                <option key={c} value={c}>{c.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label">Description</label>
            <textarea
              className="input"
              rows={4}
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Provide details…"
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={createBusy || !newTitle.trim()}>
            {createBusy ? "Creating…" : "+ Create Ticket"}
          </button>
        </form>
      </section>

      {/* Ticket list */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Your Tickets</h3>
            <p>Track and manage your support requests.</p>
          </div>
          <select
            className="input support-status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            {statusOptions.slice(1).map((s) => (
              <option key={s} value={s}>{s.replace("_", " ")}</option>
            ))}
          </select>
        </header>

        {loading ? (
          <div className="loading" />
        ) : tickets.length === 0 ? (
          <div className="empty">No tickets yet.</div>
        ) : (
          <div className="list">
            {tickets.map((ticket) => (
              <div
                key={ticket.ticket_id}
                className={`support-ticket-row${selectedTicket?.ticket_id === ticket.ticket_id ? " support-ticket-selected" : ""}`}
                onClick={() => void openTicket(ticket)}
              >
                <div className="support-ticket-top">
                  <div className="support-ticket-title">{ticket.title}</div>
                  <div className="support-ticket-pills">
                    <span className={`pill pill-${ticket.status === "resolved" || ticket.status === "closed" ? "green" : "blue"}`}>
                      {ticket.status}
                    </span>
                    <span className="pill">{ticket.priority}</span>
                  </div>
                </div>
                <div className="support-ticket-meta">
                  {ticket.category} · {new Date(ticket.created_at).toLocaleDateString()} · {ticket.message_count} messages
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Detail pane */}
      {selectedTicket && (
        <section className="panel">
          <header className="panel-header">
            <div>
              <h3>{selectedTicket.title}</h3>
              <p>{selectedTicket.description || "No description provided."}</p>
            </div>
            <div className="support-detail-actions">
              {selectedTicket.status !== "resolved" && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void changeStatus(selectedTicket.ticket_id, "resolved")}
                >
                  Mark resolved
                </button>
              )}
              <button type="button" className="btn" onClick={() => setSelectedTicket(null)}>
                Close
              </button>
            </div>
          </header>

          {detailLoading ? (
            <div className="loading" />
          ) : (
            <div className="support-messages">
              {messages.length === 0 && (
                <div className="empty">No messages yet.</div>
              )}
              {messages.map((msg) => (
                <div
                  key={msg.message_id}
                  className={`support-msg${msg.sender_type === "user" ? " support-msg-user" : " support-msg-agent"}`}
                >
                  <div className="support-msg-meta">
                    {msg.sender_type === "user" ? "You" : msg.sender_type} · {new Date(msg.created_at).toLocaleString()}
                  </div>
                  <div className="support-msg-body">{msg.body}</div>
                </div>
              ))}

              {selectedTicket.status !== "resolved" && selectedTicket.status !== "closed" && (
                <form onSubmit={(e) => void onReply(e)} className="support-reply-form">
                  <textarea
                    className="input"
                    rows={3}
                    placeholder="Write a reply…"
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    required
                  />
                  <div className="actions">
                    <button type="submit" className="btn btn-primary" disabled={replyBusy || !replyBody.trim()}>
                      {replyBusy ? "Sending…" : "Reply"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
