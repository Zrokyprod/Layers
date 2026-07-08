"use client";

import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock3,
  RefreshCw,
  Users,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { SettingsHero, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import { useDashboardStore } from "@/lib/store";
import { useMyProjects, useProjectSettings, useTeamMembers } from "@/lib/hooks";
import {
  createProjectInvitation,
  listProjectInvitations,
  revokeProjectInvitation,
} from "@/lib/api";
import { upsertProjectMember } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ProjectInvitationItem, ProjectMembershipResponse } from "@/lib/types";

const ROLE_OPTIONS = ["viewer", "member", "admin", "owner"] as const;

function roleLabel(role: string | null | undefined): string {
  const normalized = role?.trim().toLowerCase();
  if (normalized === "owner") return "Owner";
  if (normalized === "admin") return "Admin";
  if (normalized === "viewer") return "Viewer";
  return "Member";
}

function canManageTeamAccess(role: string | null | undefined): boolean {
  const normalized = role?.trim().toLowerCase();
  return normalized === "owner" || normalized === "admin";
}

function principalLabel(member: ProjectMembershipResponse): string {
  return member.email ?? member.subject;
}

function initialsFor(value: string): string {
  const clean = value.replace(/^user:/, "").trim();
  const parts = clean.split(/[^a-zA-Z0-9]+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "U";
  const second = parts[1]?.[0] ?? parts[0]?.[1] ?? "";
  return `${first}${second}`.toUpperCase();
}

function invitationStatus(invitation: ProjectInvitationItem): "accepted" | "revoked" | "pending" {
  if (invitation.accepted_at) return "accepted";
  if (invitation.revoked_at) return "revoked";
  return "pending";
}

export default function TeamPage() {
  const { selectedProject } = useDashboardStore();
  const projectQuery = useProjectSettings();
  const myProjectsQuery = useMyProjects();
  const projectId = projectQuery.data?.project_id ?? selectedProject;
  const currentMembership = projectId
    ? myProjectsQuery.data?.find((project) => project.project_id === projectId) ?? null
    : null;
  const canManageAccess = canManageTeamAccess(currentMembership?.role);
  const readOnlyAccessCopy = "Only owners and admins can manage workspace access.";
  const queryClient = useQueryClient();

  const membersQuery = useTeamMembers(projectId ?? "");
  const invitationsQuery = useQuery<ProjectInvitationItem[], Error>({
    queryKey: ["project-invitations", projectId],
    queryFn: () => listProjectInvitations(projectId as string),
    enabled: Boolean(projectId),
  });
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [busyMemberId, setBusyMemberId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [roleChangeTarget, setRoleChangeTarget] = useState<{
    member: ProjectMembershipResponse;
    role: string;
  } | null>(null);
  const [activeChangeTarget, setActiveChangeTarget] = useState<{
    member: ProjectMembershipResponse;
    active: boolean;
  } | null>(null);

  const refreshTeamData = async () => {
    setLocalError(null);
    await Promise.all([
      membersQuery.refetch(),
      invitationsQuery.refetch(),
    ]);
  };

  const inviteMutation = useMutation({
    mutationFn: ({ email, role }: { email: string; role: string }) =>
      createProjectInvitation(projectId as string, { email, role }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project-invitations", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-members", projectId] }),
      ]);
    },
  });

  const revokeInvitationMutation = useMutation({
    mutationFn: (invitationId: string) => revokeProjectInvitation(projectId as string, invitationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["project-invitations", projectId] });
    },
  });

  const updateMemberMutation = useMutation({
    mutationFn: ({
      member,
      active,
      role,
    }: {
      member: ProjectMembershipResponse;
      active?: boolean;
      role: string;
    }) => upsertProjectMember(projectId as string, { subject: member.subject, role, is_active: active }),
    onSuccess: async (updated) => {
      queryClient.setQueryData<ProjectMembershipResponse[]>(["project-members", projectId], (current) =>
        (current ?? []).map((member) => (member.membership_id === updated.membership_id ? updated : member)),
      );
      await queryClient.invalidateQueries({ queryKey: ["project-members", projectId] });
    },
  });

  const members = membersQuery.data ?? [];
  const invitations = invitationsQuery.data ?? [];
  const loading = membersQuery.isLoading || invitationsQuery.isLoading;
  const queryError = membersQuery.error?.message ?? invitationsQuery.error?.message ?? null;
  const error = localError ?? queryError;
  const inviteBusy = inviteMutation.isPending;

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    if (!projectId || !inviteEmail.trim()) return;
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      return;
    }
    setLocalError(null);
    const email = inviteEmail.trim();
    try {
      await inviteMutation.mutateAsync({
        email,
        role: inviteRole,
      });
      setInviteEmail("");
      setInviteRole("member");
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setLocalError(`Failed to send invitation to ${email}: ${msg || "Unknown error."}`);
    }
  }

  async function onRevoke(invitationId: string) {
    if (!projectId) return;
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      return;
    }
    try {
      setLocalError(null);
      await revokeInvitationMutation.mutateAsync(invitationId);
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setLocalError(msg || "Failed to revoke invitation.");
    }
  }

  function isLastActiveOwner(member: ProjectMembershipResponse): boolean {
    return member.is_active && member.role === "owner" && members.filter((item) => item.is_active && item.role === "owner").length <= 1;
  }

  function requestRoleChange(member: ProjectMembershipResponse, newRole: string) {
    if (member.role === newRole) return;
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      return;
    }
    if (isLastActiveOwner(member) && newRole !== "owner") {
      setLocalError("You cannot demote the last active owner on the project.");
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
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      setRoleChangeTarget(null);
      return;
    }
    setBusyMemberId(member.membership_id);
    setLocalError(null);
    try {
      await updateMemberMutation.mutateAsync({ member, role: newRole });
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setLocalError(msg || "Failed to update member role.");
    } finally {
      setBusyMemberId(null);
      setRoleChangeTarget(null);
    }
  }

  function requestMemberActive(member: ProjectMembershipResponse, active: boolean) {
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      return;
    }
    if (!active && isLastActiveOwner(member)) {
      setLocalError("You cannot remove the last active owner on the project.");
      return;
    }
    setActiveChangeTarget({ member, active });
  }

  async function setMemberActive() {
    if (!projectId || !activeChangeTarget) return;
    if (!canManageAccess) {
      setLocalError(readOnlyAccessCopy);
      setActiveChangeTarget(null);
      return;
    }
    const { member, active } = activeChangeTarget;
    setBusyMemberId(member.membership_id);
    setLocalError(null);
    try {
      await updateMemberMutation.mutateAsync({ member, role: member.role, active });
    } catch (e: unknown) {
      const msg = typeof e === "object" && e && "message" in e ? (e as { message?: string }).message : undefined;
      setLocalError(msg || (active ? "Failed to reactivate member." : "Failed to remove member."));
    } finally {
      setBusyMemberId(null);
      setActiveChangeTarget(null);
    }
  }

  const activeMembers = members.filter((member) => member.is_active);
  const pendingInvitationItems = invitations.filter((invitation) => invitationStatus(invitation) === "pending");
  const pendingInvites = pendingInvitationItems.length;

  return (
    <SettingsScaffold className="team-settings-page" aria-labelledby="team-settings-title">
      <SettingsHero
        ariaLabel="Members settings"
        eyebrow="Members"
        icon={<Users aria-hidden="true" />}
        title="Members"
        copy="Invite teammates, change roles, and remove access from one place."
        tone={!projectId || error ? "danger" : "success"}
        pill={projectId ? `${activeMembers.length} active` : "Project missing"}
        updatedLabel={loading ? "Refreshing" : "Settings live"}
        actions={
          <DashboardButton icon={<RefreshCw />} onClick={() => void refreshTeamData()} disabled={loading || !projectId} variant="soft">
            Refresh
          </DashboardButton>
        }
      />

      <SettingsSection
        id="invite-team-member"
        eyebrow="Access"
        title="Invite member"
        copy="Send an invitation with the right role."
        className="team-invite-section"
      >

        {!projectId ? <p className="notif-error team-error">Project context is missing. Reload the dashboard before changing members.</p> : null}
        {projectId && !canManageAccess ? (
          <p className="notice team-error">
            Your role is {roleLabel(currentMembership?.role)}. Member access is read-only for this account.
          </p>
        ) : null}
        {error && <p className="notif-error team-error">{error}</p>}

        <form onSubmit={onInvite} className="team-invite-form">
          <div className="team-invite-fields">
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
                disabled={!canManageAccess}
              />
            </div>
            <div className="field team-field-role">
              <label htmlFor="invite-role" className="field-label">Role</label>
              <select
                id="invite-role"
                className="input"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                disabled={!canManageAccess}
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
            </div>
            <DashboardButton
              type="submit"
              variant="primary"
              loading={inviteBusy}
              disabled={inviteBusy || !inviteEmail.trim() || !canManageAccess}
            >
              {inviteBusy ? "Sending..." : "Send invite"}
            </DashboardButton>
          </div>
        </form>
      </SettingsSection>

      {/* Members list */}
      <SettingsSection
        id="project-members"
        eyebrow="Members"
        title="Project members"
        copy={`${activeMembers.length} active member${activeMembers.length === 1 ? "" : "s"} · ${pendingInvites} pending invite${pendingInvites === 1 ? "" : "s"}.`}
        className="team-list-section"
      >

        {loading && members.length === 0 ? (
          <div className="loading" />
        ) : members.length === 0 ? (
          <div className="empty">No members found.</div>
        ) : (
          <div className="team-member-list">
            {members.map((m) => (
              <div key={m.membership_id} className="team-member-row">
                <div className="team-avatar">{initialsFor(principalLabel(m))}</div>

                <div className="team-member-info">
                  <div className="team-member-name-row">
                    <strong>{principalLabel(m)}</strong>
                    <span className={`team-role-badge is-${m.role}`}>{roleLabel(m.role)}</span>
                  </div>
                  <span className="provider-meta">
                    Updated {formatDateTime(m.updated_at)}
                  </span>
                </div>

                <StatusPill
                  value={m.is_active ? "active" : "inactive"}
                  label={m.is_active ? "Active" : "Inactive"}
                  tone={m.is_active ? "success" : "neutral"}
                />

                <div className="team-member-actions">
                  <label className="sr-only">Change role</label>
                  <select
                    className="input team-role-select"
                    aria-label={`Change role for ${m.email ?? m.subject}`}
                    value={m.role}
                    onChange={(e) => requestRoleChange(m, e.target.value)}
                    disabled={!canManageAccess || busyMemberId === m.membership_id}
                  >
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>{roleLabel(role)}</option>
                    ))}
                  </select>

                  {m.is_active ? (
                    <DashboardButton
                      type="button"
                      variant="soft"
                      onClick={() => requestMemberActive(m, false)}
                      disabled={!canManageAccess || busyMemberId === m.membership_id}
                      title="Remove member"
                    >
                      Remove
                    </DashboardButton>
                  ) : (
                    <DashboardButton
                      type="button"
                      variant="primary"
                      onClick={() => requestMemberActive(m, true)}
                      disabled={!canManageAccess || busyMemberId === m.membership_id}
                    >
                      Reactivate
                    </DashboardButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </SettingsSection>

      {/* Invitations list */}
      <SettingsSection
        id="pending-invitations"
        eyebrow="Invitations"
        title="Pending invites"
        copy="Revoke invites that should not become access."
        className="team-list-section"
      >

        {loading && pendingInvitationItems.length === 0 ? (
          <div className="loading" />
        ) : pendingInvitationItems.length === 0 ? (
          <div className="empty">No pending invitations.</div>
        ) : (
          <div className="team-member-list">
            {pendingInvitationItems.map((inv) => (
              <div key={inv.invitation_id} className="team-member-row team-invitation-row">
                <div className="team-inv-icon" aria-hidden="true">
                  <Clock3 />
                </div>
                <div className="team-member-info">
                  <div className="team-member-name-row">
                    <strong>{inv.email}</strong>
                    <span className={`team-role-badge is-${inv.role}`}>{roleLabel(inv.role)}</span>
                  </div>
                  <span className="provider-meta">
                    Invited by {inv.invited_by_subject ?? "workspace admin"}. Expires {formatDateTime(inv.expires_at)}.
                  </span>
                </div>
                <div className="team-invite-actions">
                  <StatusPill value="pending" label="Pending" tone="warning" />
                  <DashboardButton
                    type="button"
                    size="sm"
                    variant="danger"
                    title="Revoke invitation"
                    onClick={() => void onRevoke(inv.invitation_id)}
                    disabled={!canManageAccess}
                  >
                    Revoke
                  </DashboardButton>
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
