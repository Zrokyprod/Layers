"use client";

import { useCallback, useEffect, useState } from "react";
import { useDashboardStore } from "@/lib/store";
import {
  createProjectInvitation,
  listProjectInvitations,
  listProjectMembers,
  revokeProjectInvitation,
} from "@/lib/api";
import { upsertProjectMember } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ProjectInvitationItem, ProjectMembershipResponse } from "@/lib/types";

export default function TeamPage() {
  const { selectedProject } = useDashboardStore();

  const [members, setMembers] = useState<ProjectMembershipResponse[]>([]);
  const [invitations, setInvitations] = useState<ProjectInvitationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [busyMemberId, setBusyMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError(null);
    try {
      const [m, i] = await Promise.all([
        listProjectMembers(selectedProject),
        listProjectInvitations(selectedProject),
      ]);
      setMembers(m.items ?? []);
      setInvitations(i ?? []);
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to load team data.");
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProject || !inviteEmail.trim()) return;
    setInviteBusy(true);
    setError(null);
    try {
      await createProjectInvitation(selectedProject, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteEmail("");
      setInviteRole("member");
      await loadData();
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to send invitation.");
    } finally {
      setInviteBusy(false);
    }
  }

  async function onRevoke(invitationId: string) {
    if (!selectedProject) return;
    try {
      await revokeProjectInvitation(selectedProject, invitationId);
      setInvitations((prev) => prev.filter((i) => i.invitation_id !== invitationId));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to revoke invitation.");
    }
  }

  async function changeMemberRole(membershipId: string, subject: string, newRole: string) {
    if (!selectedProject) return;
    setBusyMemberId(membershipId);
    setError(null);
    try {
      const updated = await upsertProjectMember(selectedProject, { subject, role: newRole });
      setMembers((prev) => prev.map((m) => (m.membership_id === updated.membership_id ? updated : m)));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to update member role.");
    } finally {
      setBusyMemberId(null);
    }
  }

  async function setMemberActive(membershipId: string, subject: string, active: boolean) {
    if (!selectedProject) return;
    if (!active && !confirm("Remove this member from the project?")) return;
    setBusyMemberId(membershipId);
    setError(null);
    try {
      const updated = await upsertProjectMember(selectedProject, { subject, role: "member", is_active: active });
      setMembers((prev) => prev.map((m) => (m.membership_id === updated.membership_id ? updated : m)));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || (active ? "Failed to reactivate member." : "Failed to remove member."));
    } finally {
      setBusyMemberId(null);
    }
  }

  return (
    <>
      {/* ── Invite form ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Invite Team Member</h3>
            <p>Send an email invitation to collaborate on this project.</p>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => void loadData()} disabled={loading}>
            Refresh
          </button>
        </header>

        {error && <p className="notif-error team-error">{error}</p>}

        <form onSubmit={onInvite} className="keys-create-form team-invite-form">
          <div className="field team-field-email">
            <label htmlFor="invite-email" className="field-label">Email</label>
            <input
              id="invite-email"
              type="email"
              required
              placeholder="teammate@company.com"
              className="input"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </div>
          <div className="field team-field-role">
            <label htmlFor="invite-role" className="field-label">Role</label>
            <select
              id="invite-role"
              className="input"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
            >
              <option value="viewer">Viewer</option>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
              <option value="owner">Owner</option>
            </select>
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={inviteBusy || !inviteEmail.trim()}
          >
            {inviteBusy ? "Sending…" : "Send invite"}
          </button>
        </form>
      </section>

      {/* ── Members list ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Project Members</h3>
            <p>{members.length} member{members.length !== 1 ? "s" : ""}</p>
          </div>
        </header>

        {loading && members.length === 0 ? (
          <div className="loading" />
        ) : members.length === 0 ? (
          <div className="empty">No members found.</div>
        ) : (
          <div className="list">
            {members.map((m) => (
              <div key={m.membership_id} className="team-member-row">
                <div className="team-avatar">{(m.email ?? m.subject).slice(0, 2).toUpperCase()}</div>

                <div className="team-member-info">
                  <strong>{m.email ?? m.subject}</strong>
                  <span className="provider-meta">Role: {m.role}</span>
                </div>

                <div className="team-member-actions">
                  <label className="sr-only">Change role</label>
                  <select
                    className="input team-role-select"
                    value={m.role}
                    onChange={(e) => void changeMemberRole(m.membership_id, m.subject, e.target.value)}
                    disabled={busyMemberId === m.membership_id}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                    <option value="owner">Owner</option>
                  </select>

                  {m.is_active ? (
                    <button
                      type="button"
                      className="btn btn-soft"
                      onClick={() => void setMemberActive(m.membership_id, m.subject, false)}
                      disabled={busyMemberId === m.membership_id}
                      title="Remove member"
                    >
                      Remove
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void setMemberActive(m.membership_id, m.subject, true)}
                      disabled={busyMemberId === m.membership_id}
                    >
                      Reactivate
                    </button>
                  )}
                </div>

                <span className={`pill${m.is_active ? " pill-green" : ""}`}>{m.is_active ? "Active" : "Inactive"}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Invitations list ── */}
      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Pending Invitations</h3>
            <p>{invitations.length} invitation{invitations.length !== 1 ? "s" : ""}</p>
          </div>
        </header>

        {loading && invitations.length === 0 ? (
          <div className="loading" />
        ) : invitations.length === 0 ? (
          <div className="empty">No pending invitations.</div>
        ) : (
          <div className="list">
            {invitations.map((inv) => (
              <div key={inv.invitation_id} className="team-member-row">
                <div className="team-inv-icon">✉</div>
                <div className="team-member-info">
                  <strong>{inv.email}</strong>
                  <span className="provider-meta">
                    Role: {inv.role} · Expires {formatDateTime(inv.expires_at)}
                  </span>
                </div>
                <div className="team-invite-actions">
                  {inv.accepted_at ? (
                    <span className="pill pill-green">Accepted</span>
                  ) : inv.revoked_at ? (
                    <span className="pill">Revoked</span>
                  ) : (
                    <>
                      <span className="pill team-pill-pending">Pending</span>
                      <button
                        type="button"
                        className="notif-delete-btn"
                        title="Revoke invitation"
                        onClick={() => void onRevoke(inv.invitation_id)}
                      >
                        ✕
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
