"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { useMe, useChangePassword } from "@/lib/hooks";
import { passwordChangeSchema, type PasswordChangeFormData } from "@/lib/schemas";

export default function AccountPage() {
  const meQuery = useMe();
  const changePasswordMutation = useChangePassword();

  const [pwSuccess, setPwSuccess] = useState("");
  const [pwError, setPwError] = useState("");

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
      {/* Profile Section */}
      <section className="panel profile-section-gap">
        <div className="panel-header">
          <h3>Your Profile</h3>
          <p className="panel-sub">Account identity and login methods.</p>
        </div>

        {loadError && (
          <div className="alert-strip alert-strip-error profile-msg-gap-lg">
            {loadError}
          </div>
        )}

        {!me && !loadError && (
          <p className="muted">Loading…</p>
        )}

        {me && (
          <dl className="field-list">
            <div className="field-row">
              <dt>Email</dt>
              <dd>{me.email ?? <span className="muted">Not set</span>}</dd>
            </div>
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
              <dt>Password</dt>
              <dd>
                {me.has_password ? (
                  <span className="pill">Set</span>
                ) : (
                  <span className="muted">Not set (OAuth only)</span>
                )}
              </dd>
            </div>
            <div className="field-row">
              <dt>Member since</dt>
              <dd>
                {me.created_at
                  ? new Date(me.created_at).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })
                  : <span className="muted">Unknown</span>}
              </dd>
            </div>
          </dl>
        )}
      </section>

      {/* Change Password Section */}
      <section className="panel">
        <div className="panel-header">
          <h3>Change Password</h3>
          <p className="panel-sub">
            {me && !me.has_password
              ? "Your account uses OAuth login. Use 'Forgot Password' on the login screen to set a password."
              : "Update your login password. You must know your current password."}
          </p>
        </div>

        {me && !me.has_password ? null : (
          <form onSubmit={handleSubmit(onChangePassword)} className="profile-form-narrow">
            <div className="field profile-field-gap-md">
              <label htmlFor="current-pw" className="field-label">
                Current password
              </label>
              <input
                id="current-pw"
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
    </div>
  );
}
