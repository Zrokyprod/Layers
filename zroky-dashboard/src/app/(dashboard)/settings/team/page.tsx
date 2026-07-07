"use client";

import { type CSSProperties, type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock3,
  Crown,
  MailCheck,
  RefreshCw,
  ShieldCheck,
  UserCog,
  UserPlus,
  Users,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import { SettingsHero, SettingsMetricStrip, SettingsScaffold, SettingsSection } from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import { useDashboardStore } from "@/lib/store";
import { useMyProjects, useProjectSettings, useTeamMembers } from "@/lib/hooks";
import {
  createProjectInvitation,
  getBillingMe,
  listProjectInvitations,
  revokeProjectInvitation,
} from "@/lib/api";
import { upsertProjectMember } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { BillingMeResponse, ProjectInvitationItem, ProjectMembershipResponse } from "@/lib/types";

const ROLE_OPTIONS = ["viewer", "member", "admin", "owner"] as const;

function roleLabel(role: string | null | undefined): string {
  const normalized = role?.trim().toLowerCase();
  if (normalized === "owner") return "Owner";
  if (normalized === "admin") return "Admin";
  if (normalized === "viewer") return "Viewer";
  return "Member";
}

function roleDescription(role: string | null | undefined): string {
  const normalized = role?.trim().toLowerCase();
  if (normalized === "owner") return "Full control, billing, access, and policy authority.";
  if (normalized === "admin") return "Can manage workspace operations and most access settings.";
  if (normalized === "viewer") return "Read-only visibility into workspace state and evidence.";
  return "Can operate assigned project workflows without ownership controls.";
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
  const billingQuery = useQuery<BillingMeResponse | null, Error>({
    queryKey: ["billing-me"],
    queryFn: () => getBillingMe().catch(() => null),
    staleTime: 60_000,
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
      billingQuery.refetch(),
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
  const billing = billingQuery.data ?? null;
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
  const inactiveMembers = members.filter((member) => !member.is_active);
  const ownerCount = activeMembers.filter((member) => member.role === "owner").length;
  const adminCount = activeMembers.filter((member) => member.role === "admin").length;
  const pendingInvitationItems = invitations.filter((invitation) => invitationStatus(invitation) === "pending");
  const pendingInvites = pendingInvitationItems.length;
  const seatLimit = typeof billing?.seats === "number" && billing.seats > 0 ? billing.seats : null;
  const seatPercent = seatLimit ? Math.min(100, Math.round((activeMembers.length / seatLimit) * 100)) : 0;
  const seatMeterStyle = { "--team-seat-meter": `${seatPercent}%` } as CSSProperties;
  const planLabel = billing?.plan_code ? `${billing.plan_code.charAt(0).toUpperCase()}${billing.plan_code.slice(1)} plan` : "Plan unavailable";

  return (
    <SettingsScaffold className="team-settings-page" aria-labelledby="team-settings-title">
      <SettingsHero
        ariaLabel="Members settings"
        eyebrow="Members"
        icon={<Users aria-hidden="true" />}
        title="Workspace access"
        copy="Control who can enter this project, what authority they carry, and which invitations can still become access."
        tone={!projectId || error ? "danger" : "success"}
        pill={projectId ? `${activeMembers.length} active` : "Project missing"}
        updatedLabel={loading ? "Refreshing" : "Settings live"}
        actions={
          <DashboardButton icon={<RefreshCw />} onClick={() => void refreshTeamData()} disabled={loading || !projectId} variant="soft">
            Refresh
          </DashboardButton>
        }
      />

      <SettingsMetricStrip
        ariaLabel="Members settings summary"
        columns={4}
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
            id: "admins",
            label: "Admins",
            value: String(adminCount),
            helper: "Operational managers below owner authority",
            tone: adminCount > 0 ? "setup" : "success",
            icon: <UserCog aria-hidden="true" />,
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

      <section className="team-access-command-card" aria-label="Workspace access command center">
        <div className="team-access-command-main">
          <span className="team-command-kicker">
            <ShieldCheck aria-hidden="true" />
            Access command center
          </span>
          <h2>Every workspace action starts with a known human boundary.</h2>
          <p>
            Keep owner authority protected, invite people into the right role, and revoke pending access before it turns into a live membership.
          </p>
          <div className="team-access-rail" aria-label="Access controls">
            <span>
              <Crown aria-hidden="true" />
              Owner floor protected
            </span>
            <span>
              <UserCog aria-hidden="true" />
              Role scope explicit
            </span>
            <span>
              <MailCheck aria-hidden="true" />
              Invites remain revocable
            </span>
          </div>
        </div>

        <aside className="team-seat-card" aria-label="Seat usage">
          <div className="team-seat-card-head">
            <span>Seat usage</span>
            <strong>{seatLimit ? `${activeMembers.length} / ${seatLimit}` : `${activeMembers.length} active`}</strong>
          </div>
          <div className="team-seat-meter" style={seatMeterStyle} aria-hidden="true" />
          <div className="team-seat-facts">
            <span>{planLabel}</span>
            <span>{pendingInvites} pending invite{pendingInvites === 1 ? "" : "s"}</span>
            <span>{inactiveMembers.length} inactive member{inactiveMembers.length === 1 ? "" : "s"}</span>
          </div>
        </aside>
      </section>

      {/* Invite form */}
      <SettingsSection
        id="invite-team-member"
        eyebrow="Access"
        title="Invite a teammate"
        copy="Create a pending access grant with a clear role before the person joins the project."
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
          <div className="team-invite-panel">
            <div className="team-invite-icon" aria-hidden="true">
              <UserPlus />
            </div>
            <div>
              <strong>New access invitation</strong>
              <span>Pending invites appear below until they are accepted or revoked.</span>
            </div>
          </div>

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
        title="Project Members"
        copy={`${members.length} member${members.length !== 1 ? "s" : ""} in this project, with ${activeMembers.length} active right now.`}
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
                    {roleDescription(m.role)} Updated {formatDateTime(m.updated_at)}.
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
        title="Pending invitations"
        copy={`${pendingInvites} pending invite${pendingInvites === 1 ? "" : "s"} can still become project access.`}
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
