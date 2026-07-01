"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldCheck, UserPlus, Users } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { SettingsHero, SettingsMetricStrip, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import { useDashboardStore } from "@/lib/store";
import { useProjectSettings } from "@/lib/hooks";
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
  const projectQuery = useProjectSettings();
  const projectId = projectQuery.data?.project_id ?? selectedProject;

  const [members, setMembers] = useState<ProjectMembershipResponse[]>([]);
  const [invitations, setInvitations] = useState<ProjectInvitationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [busyMemberId, setBusyMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [roleChangeTarget, setRoleChangeTarget] = useState<{
    member: ProjectMembershipResponse;
    role: string;
  } | null>(null);
  const [activeChangeTarget, setActiveChangeTarget] = useState<{
    member: ProjectMembershipResponse;
    active: boolean;
  } | null>(null);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [m, i] = await Promise.all([
        listProjectMembers(projectId),
        listProjectInvitations(projectId),
      ]);
      setMembers(m);
      setInvitations(i ?? []);
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to load team data.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    if (!projectId || !inviteEmail.trim()) return;
    setInviteBusy(true);
    setError(null);
    const email = inviteEmail.trim();
    try {
      const created = await createProjectInvitation(projectId, {
        email,
        role: inviteRole,
      });
      setInvitations((prev) => [
        created,
        ...prev.filter((invitation) => invitation.invitation_id !== created.invitation_id),
      ]);
      setInviteEmail("");
      setInviteRole("member");
      await loadData();
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(`Failed to send invitation to ${email}: ${msg || "Unknown error."}`);
    } finally {
      setInviteBusy(false);
    }
  }

  async function onRevoke(invitationId: string) {
    if (!projectId) return;
    try {
      await revokeProjectInvitation(projectId, invitationId);
      setInvitations((prev) => prev.filter((i) => i.invitation_id !== invitationId));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to revoke invitation.");
    }
  }

  function isLastActiveOwner(member: ProjectMembershipResponse): boolean {
    return member.is_active && member.role === "owner" && members.filter((item) => item.is_active && item.role === "owner").length <= 1;
  }

  function requestRoleChange(member: ProjectMembershipResponse, newRole: string) {
    if (member.role === newRole) return;
    if (isLastActiveOwner(member) && newRole !== "owner") {
      setError("You cannot demote the last active owner on the project.");
      return;
    }
    if (member.role === "owner" || newRole === "owner" || newRole === "admin") {
      setRoleChangeTarget({ member, role: newRole });
      return;
    }
    void changeMemberRole(member, newRole);
  }

  async function changeMemberRole(member: ProjectMembershipResponse, newRole: string) {
    if (!projectId) return;
    setBusyMemberId(member.membership_id);
    setError(null);
    try {
      const updated = await upsertProjectMember(projectId, { subject: member.subject, role: newRole });
      setMembers((prev) => prev.map((m) => (m.membership_id === updated.membership_id ? updated : m)));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || "Failed to update member role.");
    } finally {
      setBusyMemberId(null);
      setRoleChangeTarget(null);
    }
  }

  function requestMemberActive(member: ProjectMembershipResponse, active: boolean) {
    if (!active && isLastActiveOwner(member)) {
      setError("You cannot remove the last active owner on the project.");
      return;
    }
    setActiveChangeTarget({ member, active });
  }

  async function setMemberActive() {
    if (!projectId || !activeChangeTarget) return;
    const { member, active } = activeChangeTarget;
    setBusyMemberId(member.membership_id);
    setError(null);
    try {
      const updated = await upsertProjectMember(projectId, { subject: member.subject, role: member.role, is_active: active });
      setMembers((prev) => prev.map((m) => (m.membership_id === updated.membership_id ? updated : m)));
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setError(msg || (active ? "Failed to reactivate member." : "Failed to remove member."));
    } finally {
      setBusyMemberId(null);
      setActiveChangeTarget(null);
    }
  }

  const activeMembers = members.filter((member) => member.is_active);
  const ownerCount = activeMembers.filter((member) => member.role === "owner").length;
  const pendingInvites = invitations.filter((invitation) => !invitation.accepted_at && !invitation.revoked_at).length;

  return (
    <SettingsScaffold className="team-settings-page" aria-labelledby="team-settings-title">
      <SettingsHero
        ariaLabel="Members settings"
        eyebrow="Members"
        icon={<Users aria-hidden="true" />}
        title="Workspace access"
        copy="Invite teammates, manage roles, and keep at least one active owner on the project."
        tone={!projectId || error ? "danger" : "success"}
        pill={projectId ? `${activeMembers.length} active` : "Project missing"}
        updatedLabel={loading ? "Refreshing" : "Settings live"}
        actions={
          <DashboardButton icon={<RefreshCw />} onClick={() => void loadData()} disabled={loading || !projectId} variant="soft">
            Refresh
          </DashboardButton>
        }
      />

      <SettingsMetricStrip
        ariaLabel="Members settings summary"
        metrics={[
          {
            id: "active-members",
            label: "Active members",
            value: String(activeMembers.length),
            helper: `${members.length} total memberships loaded`,
            tone: activeMembers.length > 0 ? "success" : "warning",
            icon: <Users aria-hidden="true" />,
          },
          {
            id: "owners",
            label: "Owners",
            value: String(ownerCount),
            helper: "Last owner is protected from demotion or removal",
            tone: ownerCount > 0 ? "success" : "danger",
            icon: <ShieldCheck aria-hidden="true" />,
          },
          {
            id: "pending-invites",
            label: "Pending invites",
            value: String(pendingInvites),
            helper: "Invites can be revoked before acceptance",
            tone: pendingInvites > 0 ? "warning" : "setup",
            icon: <UserPlus aria-hidden="true" />,
          },
        ]}
      />

      {/* Invite form */}
      <SettingsSection
        id="invite-team-member"
        eyebrow="Access"
        title="Invite team member"
        copy="Send an email invitation to collaborate on this project."
      >

        {!projectId ? <p className="notif-error team-error">Project context is missing. Reload the dashboard before changing members.</p> : null}
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
          <DashboardButton
            type="submit"
            variant="primary"
            loading={inviteBusy}
            disabled={inviteBusy || !inviteEmail.trim()}
          >
            {inviteBusy ? "Sending..." : "Send invite"}
          </DashboardButton>
        </form>
      </SettingsSection>

      {/* Members list */}
      <SettingsSection
        id="project-members"
        eyebrow="Members"
        title="Project members"
        copy={`${members.length} member${members.length !== 1 ? "s" : ""} in this project.`}
      >

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
                    aria-label={`Change role for ${m.email ?? m.subject}`}
                    value={m.role}
                    onChange={(e) => requestRoleChange(m, e.target.value)}
                    disabled={busyMemberId === m.membership_id}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                    <option value="owner">Owner</option>
                  </select>

                  {m.is_active ? (
                    <DashboardButton
                      type="button"
                      variant="soft"
                      onClick={() => requestMemberActive(m, false)}
                      disabled={busyMemberId === m.membership_id}
                      title="Remove member"
                    >
                      Remove
                    </DashboardButton>
                  ) : (
                    <DashboardButton
                      type="button"
                      variant="primary"
                      onClick={() => requestMemberActive(m, true)}
                      disabled={busyMemberId === m.membership_id}
                    >
                      Reactivate
                    </DashboardButton>
                  )}
                </div>

                <StatusPill
                  value={m.is_active ? "active" : "inactive"}
                  label={m.is_active ? "Active" : "Inactive"}
                  tone={m.is_active ? "success" : "neutral"}
                />
              </div>
            ))}
          </div>
        )}
      </SettingsSection>

      {/* Invitations list */}
      <SettingsSection
        id="pending-invitations"
        eyebrow="Invitations"
        title="Pending invitations"
        copy={`${invitations.length} invitation${invitations.length !== 1 ? "s" : ""} loaded for this project.`}
      >

        {loading && invitations.length === 0 ? (
          <div className="loading" />
        ) : invitations.length === 0 ? (
          <div className="empty">No pending invitations.</div>
        ) : (
          <div className="list">
            {invitations.map((inv) => (
              <div key={inv.invitation_id} className="team-member-row">
                <div className="team-inv-icon">INV</div>
                <div className="team-member-info">
                  <strong>{inv.email}</strong>
                  <span className="provider-meta">
                    Role: {inv.role} - Expires {formatDateTime(inv.expires_at)}
                  </span>
                </div>
                <div className="team-invite-actions">
                  {inv.accepted_at ? (
                    <StatusPill value="accepted" label="Accepted" tone="success" />
                  ) : inv.revoked_at ? (
                    <StatusPill value="revoked" label="Revoked" tone="neutral" />
                  ) : (
                    <>
                      <StatusPill value="pending" label="Pending" tone="warning" />
                      <DashboardButton
                        type="button"
                        size="sm"
                        variant="danger"
                        title="Revoke invitation"
                        onClick={() => void onRevoke(inv.invitation_id)}
                      >
                        Revoke
                      </DashboardButton>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </SettingsSection>

      {roleChangeTarget ? (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !busyMemberId && setRoleChangeTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Confirm role change"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h3>Confirm Role Change</h3>
                <p>
                  Change <strong>{roleChangeTarget.member.email ?? roleChangeTarget.member.subject}</strong> from {roleChangeTarget.member.role} to {roleChangeTarget.role}.
                </p>
              </div>
            </header>
            <div className="actions">
              <DashboardButton
                type="button"
                variant="primary"
                loading={busyMemberId === roleChangeTarget.member.membership_id}
                disabled={busyMemberId === roleChangeTarget.member.membership_id}
                onClick={() => void changeMemberRole(roleChangeTarget.member, roleChangeTarget.role)}
              >
                {busyMemberId === roleChangeTarget.member.membership_id ? "Saving..." : "Apply role change"}
              </DashboardButton>
              <DashboardButton
                type="button"
                variant="soft"
                disabled={busyMemberId === roleChangeTarget.member.membership_id}
                onClick={() => setRoleChangeTarget(null)}
              >
                Cancel
              </DashboardButton>
            </div>
          </section>
        </div>
      ) : null}

      {activeChangeTarget ? (
        <div
          className="fix-modal-backdrop"
          role="presentation"
          onClick={() => !busyMemberId && setActiveChangeTarget(null)}
        >
          <section
            className="panel keys-revoke-modal"
            role="dialog"
            aria-modal="true"
            aria-label={activeChangeTarget.active ? "Reactivate member" : "Remove member"}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="panel-header">
              <div>
                <h3>{activeChangeTarget.active ? "Reactivate Member" : "Remove Member"}</h3>
                <p>
                  {activeChangeTarget.active ? "Restore project access for" : "Remove project access for"}{" "}
                  <strong>{activeChangeTarget.member.email ?? activeChangeTarget.member.subject}</strong>.
                </p>
              </div>
            </header>
            <div className="settings-modal-facts">
              <span>Role stays <strong>{activeChangeTarget.member.role}</strong></span>
              <span>Subject <strong className="mono">{activeChangeTarget.member.subject}</strong></span>
            </div>
            <div className="actions">
              <DashboardButton
                type="button"
                variant={activeChangeTarget.active ? "primary" : "danger"}
                loading={busyMemberId === activeChangeTarget.member.membership_id}
                disabled={busyMemberId === activeChangeTarget.member.membership_id}
                onClick={() => void setMemberActive()}
              >
                {busyMemberId === activeChangeTarget.member.membership_id
                  ? "Saving..."
                  : activeChangeTarget.active
                    ? "Reactivate member"
                    : "Remove member"}
              </DashboardButton>
              <DashboardButton
                type="button"
                variant="soft"
                disabled={busyMemberId === activeChangeTarget.member.membership_id}
                onClick={() => setActiveChangeTarget(null)}
              >
                Cancel
              </DashboardButton>
            </div>
          </section>
        </div>
      ) : null}
    </SettingsScaffold>
  );
}
