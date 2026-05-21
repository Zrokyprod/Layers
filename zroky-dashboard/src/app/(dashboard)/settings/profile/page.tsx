"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { useRouter } from "next/navigation";
import { useMe, useChangePassword } from "@/lib/hooks";
import { deleteAccount } from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { passwordChangeSchema, type PasswordChangeFormData } from "@/lib/schemas";

export default function ProfilePage() {
  const meQuery = useMe();
  const changePasswordMutation = useChangePassword();

  const [pwSuccess, setPwSuccess] = useState("");
  const [pwError, setPwError] = useState("");

  // Delete account
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const router = useRouter();

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
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Password change failed.");
    }
  }

  return (
    <div className="page-content">
      {/* Identity */}
      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Your Identity</h3>
          <p className="panel-sub">Account email and connected login methods.</p>
        </header>

        {loadError && (
          <p className="field-error profile-msg-gap-lg">
            {loadError}
          </p>
        )}

        {!me && !loadError && <p className="muted">Loading…</p>}

        {me && (
          <>
            {/* Avatar + email */}
            <div className="profile-identity-row">
              <div className="profile-avatar">
                {me.email ? me.email.charAt(0).toUpperCase() : "?"}
              </div>
              <div>
                <div className="profile-email">{me.email ?? "No email set"}</div>
                <div className="profile-since">
                  Member since{" "}
                  {me.created_at
                    ? new Date(me.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
                    : "—"}
                </div>
              </div>
            </div>

            <dl className="field-list">
              <div className="field-row">
                <dt>GitHub</dt>
                <dd>
                  {me.github_login ? (
                    <span className="pill pill-green">@{me.github_login}</span>
                  ) : (
                    <span className="muted">Not connected</span>
                  )}
                </dd>
              </div>
              <div className="field-row">
                <dt>Google</dt>
                <dd>
                  {me.google_id ? (
                    <span className="pill pill-green">Connected</span>
                  ) : (
                    <span className="muted">Not connected</span>
                  )}
                </dd>
              </div>
              <div className="field-row">
                <dt>Password login</dt>
                <dd>
                  {me.has_password ? (
                    <span className="pill">Enabled</span>
                  ) : (
                    <span className="muted">Not set (OAuth only)</span>
                  )}
                </dd>
              </div>
            </dl>
          </>
        )}
      </section>

      {/* Change Password */}
      <section className="panel profile-section-gap">
        <header className="panel-header">
          <h3>Change Password</h3>
          <p className="panel-sub">
            {me && !me.has_password
              ? "Your account uses OAuth login. Use 'Forgot Password' to set a password."
              : "Requires your current password."}
          </p>
        </header>

        {me && !me.has_password ? null : (
          <form onSubmit={handleSubmit(onChangePassword)} className="profile-form-narrow">
            <div className="field profile-field-gap-md">
              <label htmlFor="cur-pw" className="field-label">
                Current password
              </label>
              <input
                id="cur-pw"
                type="password"
                className="input"
                {...register("currentPassword")}
                autoComplete="current-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.currentPassword && (
                <span className="field-error">{errors.currentPassword.message}</span>
              )}
            </div>
            <div className="field profile-field-gap-md">
              <label htmlFor="new-pw" className="field-label">
                New password
              </label>
              <input
                id="new-pw"
                type="password"
                className="input"
                {...register("newPassword")}
                autoComplete="new-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.newPassword && (
                <span className="field-error">{errors.newPassword.message}</span>
              )}
            </div>
            <div className="field profile-field-gap-lg">
              <label htmlFor="confirm-pw" className="field-label">
                Confirm new password
              </label>
              <input
                id="confirm-pw"
                type="password"
                className="input"
                {...register("confirmPassword")}
                autoComplete="new-password"
                disabled={changePasswordMutation.isPending}
              />
              {errors.confirmPassword && (
                <span className="field-error">{errors.confirmPassword.message}</span>
              )}
            </div>
            {pwError && (
              <p className="field-error profile-msg-gap-sm">
                {pwError}
              </p>
            )}
            {pwSuccess && (
              <p className="field-success profile-msg-gap-sm">
                {pwSuccess}
              </p>
            )}
            <div className="actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={changePasswordMutation.isPending}
              >
                {changePasswordMutation.isPending ? "Saving…" : "Change password"}
              </button>
            </div>
          </form>
        )}
      </section>

      {/* Two-Factor Auth */}
      <section className="panel">
        <header className="panel-header">
          <h3>Two-Factor Authentication</h3>
          <p>Add an extra layer of security via an authenticator app.</p>
        </header>
        <div className="profile-tfa-row">
          <div>
            <div className="profile-tfa-label">Authenticator App</div>
            <div className="provider-desc">Use Google Authenticator, Authy, or 1Password.</div>
          </div>
          <button type="button" className="btn btn-soft" disabled title="Coming in next release">
            Enable 2FA — Coming soon
          </button>
        </div>
      </section>

      {/* Active Sessions */}
      <section className="panel">
        <header className="panel-header">
          <h3>Active Sessions</h3>
          <p>Devices currently logged into your account.</p>
        </header>
        <div className="empty">Session tracking requires server-side storage. This feature is on the roadmap.</div>
      </section>

      {/* Danger Zone */}
      <section className="panel profile-danger-zone">
        <header className="panel-header">
          <div>
            <h3 className="profile-danger-title">Danger Zone</h3>
            <p>Permanently delete your account and all associated data. This cannot be undone.</p>
          </div>
        </header>

        {!showDeleteConfirm ? (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => setShowDeleteConfirm(true)}
          >
            Delete my account
          </button>
        ) : (
          <div className="profile-form-narrow">
            {deleteError && <div className="auth-banner auth-banner-error">{deleteError}</div>}
            <p className="profile-danger-hint">
              Type your email address to confirm deletion.
            </p>
            <div className="field profile-field-gap-md">
              <input
                type="email"
                className="input"
                placeholder={me?.email ?? "your@email.com"}
                value={deleteInput}
                onChange={(e) => setDeleteInput(e.target.value)}
              />
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn btn-danger"
                disabled={!me?.email || deleteInput !== me?.email || deleteLoading}
                onClick={async () => {
                  setDeleteError("");
                  setDeleteLoading(true);
                  try {
                    await deleteAccount(deleteInput);
                    await clearAccessToken();
                    router.push("/auth/login");
                  } catch (err: unknown) {
                    setDeleteError(err instanceof Error ? err.message : "Deletion failed.");
                  } finally {
                    setDeleteLoading(false);
                  }
                }}
              >
                {deleteLoading ? "Deleting…" : "Permanently delete account"}
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
