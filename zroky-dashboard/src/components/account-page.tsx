"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";

import { deleteAccount, getSecurityStatus, logoutAllSessions } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { useChangePassword, useMe, useUpdateMe } from "@/lib/hooks";
import { passwordChangeSchema, type PasswordChangeFormData } from "@/lib/schemas";
import type { SecurityStatusResponse } from "@/lib/types";

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
      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Your Identity</h3>
          <p className="panel-sub">Account email and connected login methods.</p>
        </header>

        {loadError && <p className="field-error profile-msg-gap-lg">{loadError}</p>}
        {!me && !loadError && <p className="muted">Loading...</p>}

        {me && (
          <>
            <div className="profile-identity-row">
              <div className="profile-avatar">
                {displayName.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="profile-email">{displayName}</div>
                <div className="profile-since">
                  {me.email ?? "No email set"} - Member since{" "}
                  {me.created_at
                    ? new Date(me.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
                    : "-"}
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
                <button type="submit" className="btn btn-primary" disabled={updateMeMutation.isPending}>
                  {updateMeMutation.isPending ? "Saving..." : "Save profile"}
                </button>
              </div>
            </form>
          </>
        )}
      </section>

      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Change Password</h3>
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
              <button type="submit" className="btn btn-primary" disabled={changePasswordMutation.isPending}>
                {changePasswordMutation.isPending ? "Saving..." : "Change password"}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Account Security</h3>
            <p>Password/OAuth status and session revocation controls.</p>
          </div>
          <button type="button" className="btn btn-soft" onClick={() => void loadSecurity()} disabled={securityLoading}>
            Refresh
          </button>
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
              <dd>{security.current_session_expires_at ? new Date(security.current_session_expires_at).toLocaleString() : "Unknown"}</dd>
            </div>
            <div className="field-row">
              <dt>Connected OAuth</dt>
              <dd>
                {security.github_connected ? "GitHub" : ""}
                {security.github_connected && security.google_connected ? ", " : ""}
                {security.google_connected ? "Google" : ""}
                {!security.github_connected && !security.google_connected ? "None" : ""}
              </dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h3>Sessions</h3>
            <p>Revoke every active browser session for this account.</p>
          </div>
        </header>
        <div className="actions">
          <button
            type="button"
            className="btn btn-danger"
            disabled={logoutAllLoading}
            onClick={() => void onLogoutAllSessions()}
          >
            {logoutAllLoading ? "Revoking..." : "Log out all sessions"}
          </button>
        </div>
      </section>

      <section className="panel profile-danger-zone">
        <header className="panel-header">
          <div>
            <h3 className="profile-danger-title">Danger Zone</h3>
            <p>Permanently delete your account and all associated data. This cannot be undone.</p>
          </div>
        </header>

        {!showDeleteConfirm ? (
          <button type="button" className="btn btn-danger" onClick={() => setShowDeleteConfirm(true)}>
            Delete my account
          </button>
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
              <button
                type="button"
                className="btn btn-danger"
                disabled={!me?.email || deleteInput !== me.email || deleteLoading}
                onClick={() => void onDeleteAccount()}
              >
                {deleteLoading ? "Deleting..." : "Permanently delete account"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteInput("");
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
