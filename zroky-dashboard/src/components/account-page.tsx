"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Fingerprint,
  KeyRound,
  LogOut,
  MonitorX,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { deleteAccount, getSecurityStatus, logoutAllSessions } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { useChangePassword, useMe, useUpdateMe } from "@/lib/hooks";
import { passwordChangeSchema, type PasswordChangeFormData } from "@/lib/schemas";
import type { SecurityStatusResponse } from "@/lib/types";
import { DashboardButton } from "./dashboard-button";

function connectedLoginLabel(security: SecurityStatusResponse | null): string {
  if (!security) return "Loading";
  const providers = [
    security.github_connected ? "GitHub" : null,
    security.google_connected ? "Google" : null,
  ].filter(Boolean);
  return providers.length > 0 ? providers.join(", ") : "None";
}

function sessionExpiryLabel(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString();
}

function accountPostureLabel(me: ReturnType<typeof useMe>["data"] | null, security: SecurityStatusResponse | null): string {
  if (!me || !security) return "Checking";
  if (me.email_verified && security.password_login_enabled && security.global_logout_available) return "Controlled";
  if (!me.email_verified) return "Review email";
  if (!security.global_logout_available) return "Session review";
  return "Limited login";
}

export default function AccountPage() {
  const router = useRouter();
  const meQuery = useMe();
  const updateMeMutation = useUpdateMe();
  const changePasswordMutation = useChangePassword();

  const [displayNameInput, setDisplayNameInput] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");
  const [profileError, setProfileError] = useState("");
  const [pwSuccess, setPwSuccess] = useState("");
  const [pwError, setPwError] = useState("");
  const [security, setSecurity] = useState<SecurityStatusResponse | null>(null);
  const [securityMessage, setSecurityMessage] = useState("");
  const [securityLoading, setSecurityLoading] = useState(true);
  const [logoutAllLoading, setLogoutAllLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<PasswordChangeFormData>({
    resolver: zodResolver(passwordChangeSchema),
  });

  const me = meQuery.data ?? null;
  const loadError = meQuery.error?.message ?? "";
  const displayName = me?.display_name?.trim() || me?.email?.split("@")[0] || "User";
  const accountPosture = securityLoading ? "Checking" : accountPostureLabel(me, security);
  const accountInitial = displayName.charAt(0).toUpperCase();
  const connectedLogin = connectedLoginLabel(security);
  const memberSince = me?.created_at
    ? new Date(me.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    : "-";

  useEffect(() => {
    if (me) {
      setDisplayNameInput(me.display_name ?? "");
    }
  }, [me]);

  const loadSecurity = useCallback(async () => {
    setSecurityLoading(true);
    setSecurityMessage("");
    try {
      setSecurity(await getSecurityStatus());
    } catch (err) {
      setSecurityMessage(err instanceof Error ? err.message : "Failed to load security status.");
    } finally {
      setSecurityLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSecurity();
  }, [loadSecurity]);

  async function onUpdateProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileSuccess("");
    setProfileError("");
    try {
      const nextName = displayNameInput.trim() || null;
      await updateMeMutation.mutateAsync({ displayName: nextName });
      setProfileSuccess("Profile updated.");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Profile update failed.");
    }
  }

  async function onChangePassword(data: PasswordChangeFormData) {
    setPwSuccess("");
    setPwError("");
    try {
      const res = await changePasswordMutation.mutateAsync({
        currentPassword: data.currentPassword,
        newPassword: data.newPassword,
      });
      setPwSuccess(res.detail ?? "Password changed successfully.");
      reset();
      await loadSecurity();
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Password change failed.");
    }
  }

  async function onLogoutAllSessions() {
    setLogoutAllLoading(true);
    setSecurityMessage("");
    try {
      await logoutAllSessions();
      await clearAccessToken();
      router.push("/login");
    } catch (err) {
      setSecurityMessage(err instanceof Error ? err.message : "Failed to revoke sessions.");
    } finally {
      setLogoutAllLoading(false);
    }
  }

  async function onDeleteAccount() {
    setDeleteError("");
    setDeleteLoading(true);
    try {
      await deleteAccount(deleteInput);
      await clearAccessToken();
      router.push("/login");
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Deletion failed.");
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="page-content account-page settings-profile-page">
      <section className="account-command-hero" aria-label="Account security overview">
        <div className="account-hero-copy">
          <span className="account-eyebrow">
            <Fingerprint aria-hidden="true" />
            Personal account
          </span>
          <h1>{displayName}</h1>
          <p>Manage the identity, login method, and browser sessions used to access protected Zroky workspaces.</p>
          <div className="account-hero-meta" aria-label="Account identifiers">
            <span>{me?.email ?? "No email set"}</span>
            <span>{me?.user_id ?? "User loading"}</span>
            <span>Member since {memberSince}</span>
          </div>
        </div>
        <aside className={`account-posture-card is-${accountPosture.toLowerCase().replaceAll(" ", "-")}`}>
          <span>Account posture</span>
          <strong>{accountPosture}</strong>
          <small>
            {securityLoading
              ? "Loading current session and login status."
              : securityMessage
                ? "Security status could not be loaded."
                : "Identity and session controls are backed by the account API."}
          </small>
        </aside>
      </section>

      <section className="account-status-grid" aria-label="Account control summary">
        <article className={me?.email_verified ? "account-status-card is-ready" : "account-status-card is-warn"}>
          <ShieldCheck aria-hidden="true" />
          <span>Email verification</span>
          <strong>{me?.email_verified ? "Verified" : me ? "Not verified" : "Loading"}</strong>
          <small>Used for account recovery and workspace invites.</small>
        </article>
        <article className={security?.password_login_enabled ? "account-status-card is-ready" : "account-status-card is-warn"}>
          <KeyRound aria-hidden="true" />
          <span>Password login</span>
          <strong>{securityLoading ? "Loading" : security?.password_login_enabled ? "Enabled" : "OAuth only"}</strong>
          <small>{me?.has_password ? "Password changes are available." : "Use recovery flow to set a password."}</small>
        </article>
        <article className={connectedLogin !== "None" && connectedLogin !== "Loading" ? "account-status-card is-ready" : "account-status-card"}>
          <UserRound aria-hidden="true" />
          <span>Connected login</span>
          <strong>{connectedLogin}</strong>
          <small>OAuth providers linked to this account.</small>
        </article>
        <article className={security?.global_logout_available ? "account-status-card is-ready" : "account-status-card is-warn"}>
          <MonitorX aria-hidden="true" />
          <span>Session control</span>
          <strong>{securityLoading ? "Loading" : security?.global_logout_available ? "Available" : "Unavailable"}</strong>
          <small>Expires {securityLoading ? "after security status loads" : sessionExpiryLabel(security?.current_session_expires_at)}.</small>
        </article>
      </section>

      <section className="panel profile-section-gap" id="identity">
        <header className="panel-header">
          <h3>Your identity</h3>
          <p className="panel-sub">Account email and connected login methods.</p>
        </header>

        {loadError && <p className="field-error profile-msg-gap-lg">{loadError}</p>}
        {!me && !loadError && <p className="muted">Loading...</p>}

        {me && (
          <>
            <div className="profile-identity-row">
              <div className="profile-avatar">
                {accountInitial}
              </div>
              <div>
                <div className="profile-email">{displayName}</div>
                <div className="profile-since">
                  {me.email ?? "No email set"} - Member since {memberSince}
                </div>
              </div>
            </div>

            <dl className="field-list">
              <div className="field-row">
                <dt>Display name</dt>
                <dd>{me.display_name ? <span>{me.display_name}</span> : <span className="muted">Not set</span>}</dd>
              </div>
              <div className="field-row">
                <dt>Email verification</dt>
                <dd>{me.email_verified ? <span className="pill pill-green">Verified</span> : <span className="pill">Not verified</span>}</dd>
              </div>
              <div className="field-row">
                <dt>GitHub</dt>
                <dd>{me.github_login ? <span className="pill pill-green">@{me.github_login}</span> : <span className="muted">Not connected</span>}</dd>
              </div>
              <div className="field-row">
                <dt>Google</dt>
                <dd>{me.google_id ? <span className="pill pill-green">Connected</span> : <span className="muted">Not connected</span>}</dd>
              </div>
              <div className="field-row">
                <dt>Password login</dt>
                <dd>{me.has_password ? <span className="pill">Enabled</span> : <span className="muted">Not set (OAuth only)</span>}</dd>
              </div>
            </dl>

            <form onSubmit={onUpdateProfile} className="profile-form-narrow profile-edit-form">
              <div className="field profile-field-gap-md">
                <label htmlFor="display-name" className="field-label">Display name</label>
                <input
                  id="display-name"
                  type="text"
                  className="input"
                  value={displayNameInput}
                  onChange={(event) => setDisplayNameInput(event.target.value)}
                  autoComplete="name"
                  maxLength={80}
                  disabled={updateMeMutation.isPending}
                />
                <span className="field-hint">Used in account and team surfaces. Leave blank to clear it.</span>
              </div>
              {profileError && <p className="field-error profile-msg-gap-sm">{profileError}</p>}
              {profileSuccess && <p className="field-success profile-msg-gap-sm">{profileSuccess}</p>}
              <div className="actions">
                <DashboardButton type="submit" variant="primary" loading={updateMeMutation.isPending}>
                  {updateMeMutation.isPending ? "Saving..." : "Save profile"}
                </DashboardButton>
              </div>
            </form>
          </>
        )}
      </section>

      <section className="panel profile-section-gap" id="login-method">
        <header className="panel-header">
          <h3>Change password</h3>
          <p className="panel-sub">
            {me && !me.has_password
              ? "Your account uses OAuth login. Use Forgot Password to set a password."
              : "Requires your current password."}
          </p>
        </header>

        {me && !me.has_password ? null : (
          <form onSubmit={handleSubmit(onChangePassword)} className="profile-form-narrow">
            <div className="field profile-field-gap-md">
              <label htmlFor="cur-pw" className="field-label">Current password</label>
              <input
                id="cur-pw"
                type="password"
                className="input"
                {...register("currentPassword")}
                autoComplete="current-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.currentPassword && <span className="field-error">{errors.currentPassword.message}</span>}
            </div>
            <div className="field profile-field-gap-md">
              <label htmlFor="new-pw" className="field-label">New password</label>
              <input
                id="new-pw"
                type="password"
                className="input"
                {...register("newPassword")}
                autoComplete="new-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.newPassword && <span className="field-error">{errors.newPassword.message}</span>}
            </div>
            <div className="field profile-field-gap-lg">
              <label htmlFor="confirm-pw" className="field-label">Confirm new password</label>
              <input
                id="confirm-pw"
                type="password"
                className="input"
                {...register("confirmPassword")}
                autoComplete="new-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.confirmPassword && <span className="field-error">{errors.confirmPassword.message}</span>}
            </div>
            {pwError && <p className="field-error profile-msg-gap-sm">{pwError}</p>}
            {pwSuccess && <p className="field-success profile-msg-gap-sm">{pwSuccess}</p>}
            <div className="actions">
              <DashboardButton type="submit" variant="primary" loading={changePasswordMutation.isPending}>
                {changePasswordMutation.isPending ? "Saving..." : "Change password"}
              </DashboardButton>
            </div>
          </form>
        )}
      </section>

      <section className="panel" id="session-control">
        <header className="panel-header">
          <div>
            <h3>Account security</h3>
            <p>Password/OAuth status and session revocation controls.</p>
          </div>
          <DashboardButton type="button" variant="soft" onClick={() => void loadSecurity()} loading={securityLoading}>
            Refresh
          </DashboardButton>
        </header>

        {securityMessage && <p className="field-error profile-msg-gap-sm">{securityMessage}</p>}
        {securityLoading ? (
          <p className="muted">Loading...</p>
        ) : security ? (
          <dl className="field-list">
            <div className="field-row">
              <dt>Password login</dt>
              <dd>{security.password_login_enabled ? <span className="pill">Enabled</span> : <span className="muted">OAuth only</span>}</dd>
            </div>
            <div className="field-row">
              <dt>Current session expires</dt>
              <dd>{sessionExpiryLabel(security.current_session_expires_at)}</dd>
            </div>
            <div className="field-row">
              <dt>Connected OAuth</dt>
              <dd>{connectedLoginLabel(security)}</dd>
            </div>
            <div className="field-row">
              <dt>Global session revoke</dt>
              <dd>{security.global_logout_available ? <span className="pill pill-green">Available</span> : <span className="muted">Unavailable</span>}</dd>
            </div>
          </dl>
        ) : null}
        <div className="actions">
          <DashboardButton
            type="button"
            variant="danger"
            disabled={logoutAllLoading || security?.global_logout_available === false}
            loading={logoutAllLoading}
            icon={<LogOut />}
            onClick={() => void onLogoutAllSessions()}
          >
            {logoutAllLoading ? "Revoking..." : "Log out all sessions"}
          </DashboardButton>
        </div>
      </section>

      <section className="panel profile-danger-zone" id="danger-zone">
        <header className="panel-header">
          <div>
            <h3 className="profile-danger-title">Danger zone</h3>
            <p>Permanently delete your account and all associated data. This cannot be undone.</p>
          </div>
        </header>

        {!showDeleteConfirm ? (
          <DashboardButton type="button" variant="danger" icon={<AlertTriangle />} onClick={() => setShowDeleteConfirm(true)}>
            Delete my account
          </DashboardButton>
        ) : (
          <div className="profile-form-narrow">
            {deleteError && <div className="auth-banner auth-banner-error">{deleteError}</div>}
            <p className="profile-danger-hint">Type your email address to confirm deletion.</p>
            <div className="field profile-field-gap-md">
              <input
                type="email"
                className="input"
                placeholder={me?.email ?? "your@email.com"}
                value={deleteInput}
                onChange={(event) => setDeleteInput(event.target.value)}
              />
            </div>
            <div className="actions">
              <DashboardButton
                type="button"
                variant="danger"
                icon={<CheckCircle2 />}
                disabled={!me?.email || deleteInput !== me.email || deleteLoading}
                loading={deleteLoading}
                onClick={() => void onDeleteAccount()}
              >
                {deleteLoading ? "Deleting..." : "Permanently delete account"}
              </DashboardButton>
              <DashboardButton
                type="button"
                variant="soft"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteInput("");
                }}
              >
                Cancel
              </DashboardButton>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
