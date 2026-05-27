"use client";

import { useEffect, useMemo, useState } from "react";

import {
  useOwnerSupportTickets,
  useOwnerSupportTicket,
  useReplyOwnerSupportTicket,
  useUpdateOwnerSupportTicket,
} from "@/lib/hooks";
import type { OwnerSupportTicketItem } from "@/lib/owner-api";

const STATUS_OPTIONS = ["open", "waiting", "resolved", "closed"];
const PRIORITY_OPTIONS = ["low", "normal", "high", "urgent"];

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function ticketTone(ticket: OwnerSupportTicketItem): "ok" | "warn" | "danger" | "neutral" {
  if (ticket.status === "resolved" || ticket.status === "closed") return "ok";
  if (ticket.priority === "urgent" || ticket.priority === "high") return "danger";
  if (ticket.status === "waiting") return "neutral";
  return "warn";
}

function TicketBadge({ ticket }: { ticket: OwnerSupportTicketItem }) {
  return (
    <span className={`owner-ops-badge owner-ops-badge-${ticketTone(ticket)}`}>
      {ticket.priority} - {ticket.status}
    </span>
  );
}

export default function OwnerSupportPage() {
  const [status, setStatus] = useState("open");
  const [priority, setPriority] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftAssignee, setDraftAssignee] = useState("");
  const [draftPriority, setDraftPriority] = useState("normal");
  const [draftStatus, setDraftStatus] = useState("open");
  const [replyBody, setReplyBody] = useState("");
  const [internalReply, setInternalReply] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  const ticketsQuery = useOwnerSupportTickets({
    status: status || undefined,
    priority: priority || undefined,
    assigned_to: assignedTo || undefined,
    limit: 100,
  });
  const updateTicket = useUpdateOwnerSupportTicket();
  const replyTicket = useReplyOwnerSupportTicket();

  const tickets = useMemo(() => ticketsQuery.data?.items ?? [], [ticketsQuery.data?.items]);
  const selected = useMemo(
    () => tickets.find((ticket) => ticket.ticket_id === selectedId) ?? tickets[0] ?? null,
    [selectedId, tickets],
  );
  const detailQuery = useOwnerSupportTicket(selected?.ticket_id ?? null);
  const detail = detailQuery.data ?? null;

  useEffect(() => {
    if (!selected) return;
    setDraftAssignee(selected.assigned_to ?? "");
    setDraftPriority(selected.priority);
    setDraftStatus(selected.status);
  }, [selected]);

  function syncSelected(ticket: OwnerSupportTicketItem) {
    setSelectedId(ticket.ticket_id);
    setDraftAssignee(ticket.assigned_to ?? "");
    setDraftPriority(ticket.priority);
    setDraftStatus(ticket.status);
    setActionMsg("");
  }

  async function saveTicket() {
    if (!selected) return;
    setActionMsg("");
    try {
      await updateTicket.mutateAsync({
        ticketId: selected.ticket_id,
        body: {
          assigned_to: draftAssignee.trim() || undefined,
          priority: draftPriority,
          status: draftStatus,
        },
      });
      setActionMsg("Ticket updated.");
    } catch (error) {
      setActionMsg(error instanceof Error ? error.message : "Ticket update failed.");
    }
  }

  async function sendReply() {
    if (!selected || !replyBody.trim()) return;
    setActionMsg("");
    try {
      await replyTicket.mutateAsync({
        ticketId: selected.ticket_id,
        body: { body: replyBody.trim(), is_internal: internalReply },
      });
      setReplyBody("");
      setInternalReply(false);
      setActionMsg(internalReply ? "Internal note saved." : "Reply sent.");
    } catch (error) {
      setActionMsg(error instanceof Error ? error.message : "Reply failed.");
    }
  }

  return (
    <div className="owner-page owner-support-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Support</h2>
          <p className="hint">Ticket triage, assignment, priority, status and owner replies.</p>
        </div>
        <button className="btn btn-soft" onClick={() => ticketsQuery.refetch()} disabled={ticketsQuery.isFetching}>
          Refresh
        </button>
      </div>

      {ticketsQuery.error ? <div className="alert-strip alert-strip-error">{ticketsQuery.error.message}</div> : null}
      {actionMsg ? (
        <div className={actionMsg.includes("failed") || actionMsg.includes("HTTP") ? "alert-strip alert-strip-error" : "alert-strip"}>
          {actionMsg}
        </div>
      ) : null}

      <section className="panel owner-panel-filter">
        <div className="owner-filter-row">
          <label className="owner-filter-group">
            <span className="owner-filter-label">Status</span>
            <select className="owner-select" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="owner-filter-group">
            <span className="owner-filter-label">Priority</span>
            <select className="owner-select" value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="">All priorities</option>
              {PRIORITY_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="owner-filter-group">
            <span className="owner-filter-label">Assigned To</span>
            <input
              className="input"
              value={assignedTo}
              onChange={(event) => setAssignedTo(event.target.value)}
              placeholder="owner email or handle"
            />
          </label>
        </div>
      </section>

      <div className="owner-support-layout">
        <section className="owner-table-wrap">
          <table className="owner-table">
            <thead>
              <tr>
                {["Ticket", "Priority", "Assignee", "Tenant", "Updated"].map((header) => (
                  <th key={header} className="owner-th">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ticketsQuery.isLoading ? (
                <tr><td colSpan={5} className="owner-td owner-td-empty">Loading tickets...</td></tr>
              ) : tickets.length === 0 ? (
                <tr><td colSpan={5} className="owner-td owner-td-empty">No tickets match the current filters.</td></tr>
              ) : (
                tickets.map((ticket) => (
                  <tr
                    key={ticket.ticket_id}
                    className={`owner-tr${selected?.ticket_id === ticket.ticket_id ? " owner-tr-selected" : ""}`}
                    onClick={() => syncSelected(ticket)}
                  >
                    <td className="owner-td">
                      <strong>{ticket.title}</strong>
                      <div className="hint">{ticket.category ?? "general"} - {ticket.message_count} messages</div>
                    </td>
                    <td className="owner-td"><TicketBadge ticket={ticket} /></td>
                    <td className="owner-td owner-td-truncate">{ticket.assigned_to ?? "Unassigned"}</td>
                    <td className="owner-td-mono">{ticket.tenant_id ?? "tenant:unknown"}</td>
                    <td className="owner-td owner-td-ts">{formatDate(ticket.updated_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        <aside className="panel owner-support-detail">
          <div className="panel-header">Ticket Controls</div>
          {!selected ? (
            <p className="hint owner-support-empty">Select a ticket to update it.</p>
          ) : (
            <div className="owner-support-detail-body">
              <div>
                <span className="owner-section-label">Selected ticket</span>
                <h3>{selected.title}</h3>
                <p className="hint">{selected.ticket_id}</p>
                {selected.description ? <p className="owner-support-description">{selected.description}</p> : null}
                <div className="owner-support-meta">
                  <span>{selected.email ?? selected.subject ?? "unknown requester"}</span>
                  <span>{selected.tenant_id ?? "tenant:unknown"}</span>
                  <span>{formatDate(selected.created_at)}</span>
                </div>
              </div>

              <label className="field">
                <span className="field-label">Assignee</span>
                <input
                  className="input"
                  value={draftAssignee}
                  onChange={(event) => setDraftAssignee(event.target.value)}
                  placeholder="owner email or handle"
                />
              </label>

              <div className="owner-support-control-grid">
                <label className="field">
                  <span className="field-label">Priority</span>
                  <select className="owner-select" value={draftPriority} onChange={(event) => setDraftPriority(event.target.value)}>
                    {PRIORITY_OPTIONS.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field-label">Status</span>
                  <select className="owner-select" value={draftStatus} onChange={(event) => setDraftStatus(event.target.value)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
              </div>

              <button className="btn btn-primary" onClick={saveTicket} disabled={updateTicket.isPending}>
                {updateTicket.isPending ? "Saving..." : "Save ticket"}
              </button>

              <section className="owner-support-thread">
                <div className="owner-support-thread-head">
                  <span className="owner-section-label">Message thread</span>
                  {detailQuery.isFetching ? <span className="hint">Refreshing</span> : null}
                </div>
                {detailQuery.isLoading ? (
                  <p className="hint">Loading messages...</p>
                ) : (detail?.messages ?? []).length === 0 ? (
                  <p className="hint">No messages on this ticket yet.</p>
                ) : (
                  <div className="owner-support-messages">
                    {(detail?.messages ?? []).map((message) => (
                      <article
                        key={message.message_id}
                        className={`owner-support-message${message.is_internal ? " owner-support-message-internal" : ""}`}
                      >
                        <div className="owner-support-message-head">
                          <strong>{message.sender_type}</strong>
                          <span>{message.sender_subject ?? "unknown"} - {formatDate(message.created_at)}</span>
                        </div>
                        <p>{message.body}</p>
                        {message.is_internal ? <span className="owner-ops-badge owner-ops-badge-neutral">internal</span> : null}
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <label className="field">
                <span className="field-label">Reply</span>
                <textarea
                  className="input owner-support-reply"
                  value={replyBody}
                  onChange={(event) => setReplyBody(event.target.value)}
                  placeholder="Write a customer reply or internal note"
                />
              </label>
              <label className="owner-flag-checkbox">
                <input
                  type="checkbox"
                  checked={internalReply}
                  onChange={(event) => setInternalReply(event.target.checked)}
                />
                Internal note
              </label>
              <button className="btn btn-soft" onClick={sendReply} disabled={replyTicket.isPending || !replyBody.trim()}>
                {replyTicket.isPending ? "Sending..." : internalReply ? "Save note" : "Send reply"}
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
