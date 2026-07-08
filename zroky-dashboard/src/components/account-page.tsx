"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  CreditCard,
  Fingerprint,
  Gauge,
  KeyRound,
  LogOut,
  MonitorX,
  ReceiptText,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import {
  confirmTotpMfa,
  deleteAccount,
  disableTotpMfa,
  getBillingMe,
  getBillingUsage,
  getSecurityStatus,
  logoutAllSessions,
  startTotpMfa,
} from "@/lib/api";
import { clearAccessToken } from "@/lib/auth";
import { useChangePassword, useMe, useUpdateMe } from "@/lib/hooks";
import { passwordChangeSchema, type PasswordChangeFormData } from "@/lib/schemas";
import type { BillingMeResponse, BillingUsageMeter, BillingUsageResponse, SecurityStatusResponse } from "@/lib/types";
import { formatPlanLabel } from "./feature-gate";
import { DashboardButton, DashboardButtonLink } from "./dashboard-button";

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
  const hasLoginMethod = security.password_login_enabled || security.github_connected || security.google_connected;
  if (me.email_verified && hasLoginMethod && security.global_logout_available) return "Controlled";
  if (!me.email_verified) return "Review email";
  if (!security.global_logout_available) return "Session review";
  return "Limited login";
}

function formatBillingMeter(meter: BillingUsageMeter | null | undefined): string {
  if (!meter) return "Loading";
  const used = meter.used.toLocaleString();
  if (meter.unlimited || meter.limit == null) return `${used} used`;
  return `${used} / ${meter.limit.toLocaleString()}`;
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
  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [billingUsage, setBillingUsage] = useState<BillingUsageResponse | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const [billingMessage, setBillingMessage] = useState("");
  const [logoutAllLoading, setLogoutAllLoading] = useState(false);
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; otpauthUri: string } | null>(null);
  const [mfaPassword, setMfaPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaMessage, setMfaMessage] = useState("");
  const [mfaError, setMfaError] = useState("");
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
  const accountPosture = securityLoading
    ? "Checking"
    : securityMessage && !security
      ? "Needs review"
      : accountPostureLabel(me, security);
  const accountInitial = displayName.charAt(0).toUpperCase();
  const connectedLogin = securityLoading ? "Loading" : security ? connectedLoginLabel(security) : "Unavailable";
  const memberSince = me?.created_at
    ? new Date(me.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    : "-";
  const sessionStatus = securityLoading
    ? "Loading"
    : security?.global_logout_available
      ? "Available"
      : security
        ? "Unavailable"
        : "Needs refresh";
  const sessionExpiry = securityLoading
    ? "Loading expiry"
    : security?.current_session_expires_at
      ? `Expires ${sessionExpiryLabel(security.current_session_expires_at)}`
      : "Expiry unavailable";
  const passwordStatus = securityLoading
    ? "Loading"
    : security?.password_login_enabled
      ? "Enabled"
      : security
        ? "OAuth only"
        : "Needs refresh";
  const passwordHelp = me?.has_password
    ? "Password changes are available."
    : "Use account recovery to set a password.";
  const planLabel = billingLoading ? "Loading plan" : formatPlanLabel(billingMe?.plan_code);
  const planStatus = billingLoading ? "Loading" : billingMe?.status ?? "Unavailable";
  const planPayment = billingLoading
    ? "Loading payment"
    : billingMe?.payment_subscription_ref
      ? "Payment confirmed"
      : billingMe?.payment_request_ref
        ? "Payment pending"
        : billingMe?.payment_provider === "manual"
          ? "Manual billing"
          : "No paid checkout";
  const accountPlanItems = [
    {
      icon: <ShieldCheck aria-hidden="true" />,
      label: "Protected actions",
      value: formatBillingMeter(billingUsage?.protected_actions),
    },
    {
      icon: <ReceiptText aria-hidden="true" />,
      label: "Receipts",
      value: formatBillingMeter(billingUsage?.action_receipts),
    },
    {
      icon: <Gauge aria-hidden="true" />,
      label: "Connectors",
      value: formatBillingMeter(billingUsage?.active_connectors),
    },
  ];
  const accountStatusItems = [
    {
      icon: <ShieldCheck aria-hidden="true" />,
      label: "Email",
      value: me?.email_verified ? "Verified" : me ? "Not verified" : "Loading",
      detail: "Recovery and workspace invites.",
      tone: me?.email_verified ? "ready" : "warn",
    },
    {
      icon: <KeyRound aria-hidden="true" />,
      label: "Password",
      value: passwordStatus,
      detail: passwordHelp,
      tone: security?.password_login_enabled ? "ready" : "neutral",
    },
    {
      icon: <UserRound aria-hidden="true" />,
      label: "Connected login",
      value: connectedLogin,
      detail: connectedLogin === "None" ? "No OAuth provider connected." : "OAuth provider status.",
      tone: connectedLogin !== "None" && connectedLogin !== "Loading" && connectedLogin !== "Unavailable" ? "ready" : "neutral",
    },
    {
      icon: <Fingerprint aria-hidden="true" />,
      label: "Authenticator",
      value: securityLoading ? "Loading" : security?.two_factor_enabled ? "Enabled" : "Not enabled",
      detail: "Required after password sign-in.",
      tone: security?.two_factor_enabled ? "ready" : "warn",
    },
    {
      icon: <MonitorX aria-hidden="true" />,
      label: "Sessions",
      value: sessionStatus,
      detail: sessionExpiry,
      tone: security?.global_logout_available ? "ready" : "warn",
    },
  ];

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

  const loadBilling = useCallback(async () => {
    setBillingLoading(true);
    setBillingMessage("");
    try {
      const [meBilling, usage] = await Promise.all([getBillingMe(), getBillingUsage()]);
      setBillingMe(meBilling);
      setBillingUsage(usage);
    } catch (err) {
      setBillingMessage(err instanceof Error ? err.message : "Failed to load billing status.");
    } finally {
      setBillingLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBilling();
  }, [loadBilling]);

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

  async function onStartMfa() {
    setMfaLoading(true);
    setMfaMessage("");
    setMfaError("");
    try {
      const res = await startTotpMfa();
      setMfaSetup({ secret: res.secret, otpauthUri: res.otpauth_uri });
      setMfaMessage("Scan the authenticator URI or enter the setup key, then confirm with a 6-digit code.");
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : "Failed to start authenticator setup.");
    } finally {
      setMfaLoading(false);
    }
  }

  async function onConfirmMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMfaLoading(true);
    setMfaMessage("");
    setMfaError("");
    try {
      const res = await confirmTotpMfa(mfaPassword, mfaCode);
      setMfaMessage(res.detail);
      setMfaSetup(null);
      setMfaPassword("");
      setMfaCode("");
      await clearAccessToken();
      router.push("/login");
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : "Failed to enable authenticator MFA.");
    } finally {
      setMfaLoading(false);
    }
  }

  async function onDisableMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMfaLoading(true);
    setMfaMessage("");
    setMfaError("");
    try {
      const res = await disableTotpMfa(mfaPassword, mfaCode);
      setMfaMessage(res.detail);
      setMfaPassword("");
      setMfaCode("");
      await clearAccessToken();
      router.push("/login");
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : "Failed to disable authenticator MFA.");
    } finally {
      setMfaLoading(false);
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
      <section className="account-overview-panel" aria-label="Account overview">
        <div className="account-overview-main">
          <div className="account-avatar">{accountInitial}</div>
          <div className="account-overview-copy">
            <span className="account-eyebrow">
              <Fingerprint aria-hidden="true" />
              Personal account
            </span>
            <h1>{displayName}</h1>
            <p>{me?.email ?? "No email set"}</p>
          </div>
        </div>
        <div className="account-overview-side">
          <span className={`account-posture-badge is-${accountPosture.toLowerCase().replaceAll(" ", "-")}`}>
            {accountPosture}
          </span>
          <span>Member since {memberSince}</span>
        </div>
      </section>

      <section className="panel account-plan-panel" aria-label="Account plan">
        <header className="account-panel-header">
          <div>
            <h3>Plan and workspace access</h3>
            <p>Subscription state used by project quotas and protected-action limits.</p>
          </div>
          <DashboardButtonLink href="/settings/billing" variant="soft" icon={<CreditCard />}>
            Open billing
          </DashboardButtonLink>
        </header>

        {billingMessage ? <p className="account-message is-error">{billingMessage}</p> : null}

        <div className="account-plan-card">
          <div className="account-plan-primary">
            <span className="account-plan-kicker">Current plan</span>
            <strong>{planLabel}</strong>
            <small>{planPayment}</small>
          </div>
          <span className="account-plan-status">{planStatus}</span>
        </div>

        <div className="account-plan-meter-grid">
          {accountPlanItems.map((item) => (
            <article key={item.label}>
              <span>{item.icon}</span>
              <strong>{item.value}</strong>
              <small>{item.label}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="panel account-security-panel" aria-label="Account security">
        <header className="account-panel-header">
          <div>
            <h3>Account security</h3>
            <p>Email, login, and session status.</p>
          </div>
          <DashboardButton type="button" variant="soft" onClick={() => void loadSecurity()} loading={securityLoading}>
            Refresh
          </DashboardButton>
        </header>

        {securityMessage && <p className="account-message is-error">{securityMessage}</p>}

        <div className="account-status-list">
          {accountStatusItems.map((item) => (
            <article className={`account-status-row is-${item.tone}`} key={item.label}>
              <span className="account-status-icon">{item.icon}</span>
              <span className="account-status-copy">
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </span>
              <span className="account-status-value">{item.value}</span>
            </article>
          ))}
        </div>

        <div className="profile-form-narrow profile-edit-form">
          <h4 className="account-security-subtitle">Authenticator app</h4>
          <p className="panel-sub">
            Protect approvals with a 6-digit code after password sign-in.
          </p>
          {mfaError ? <p className="account-message is-error">{mfaError}</p> : null}
          {mfaMessage ? <p className="account-message is-success">{mfaMessage}</p> : null}

          {!security?.two_factor_enabled && !mfaSetup ? (
            <DashboardButton
              type="button"
              variant="primary"
              loading={mfaLoading}
              onClick={() => void onStartMfa()}
              disabled={mfaLoading || !security?.password_login_enabled}
            >
              Set up authenticator
            </DashboardButton>
          ) : null}

          {mfaSetup ? (
            <form onSubmit={onConfirmMfa} className="profile-edit-form">
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="mfa-secret">Setup key</label>
                <input id="mfa-secret" className="input" value={mfaSetup.secret} readOnly />
              </div>
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="mfa-uri">Authenticator URI</label>
                <input id="mfa-uri" className="input" value={mfaSetup.otpauthUri} readOnly />
              </div>
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="mfa-password">Current password</label>
                <input
                  id="mfa-password"
                  className="input"
                  type="password"
                  value={mfaPassword}
                  onChange={(event) => setMfaPassword(event.target.value)}
                  autoComplete="current-password"
                />
              </div>
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="mfa-code">Authenticator code</label>
                <input
                  id="mfa-code"
                  className="input"
                  inputMode="numeric"
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value)}
                  autoComplete="one-time-code"
                />
              </div>
              <DashboardButton type="submit" variant="primary" loading={mfaLoading}>
                Enable authenticator
              </DashboardButton>
            </form>
          ) : null}

          {security?.two_factor_enabled ? (
            <form onSubmit={onDisableMfa} className="profile-edit-form">
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="disable-mfa-password">Current password</label>
                <input
                  id="disable-mfa-password"
                  className="input"
                  type="password"
                  value={mfaPassword}
                  onChange={(event) => setMfaPassword(event.target.value)}
                  autoComplete="current-password"
                />
              </div>
              <div className="field profile-field-gap-md">
                <label className="field-label" htmlFor="disable-mfa-code">Authenticator code</label>
                <input
                  id="disable-mfa-code"
                  className="input"
                  inputMode="numeric"
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value)}
                  autoComplete="one-time-code"
                />
              </div>
              <DashboardButton type="submit" variant="danger" loading={mfaLoading}>
                Disable authenticator
              </DashboardButton>
            </form>
          ) : null}
        </div>

        <div className="account-security-actions">
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

      <section className="panel profile-section-gap" id="identity">
        <header className="account-panel-header">
          <h3>Your identity</h3>
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
                <dt>Email</dt>
                <dd>{me.email ?? "No email set"}</dd>
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
              </div>
              {profileError && <p className="account-message is-error">{profileError}</p>}
              {profileSuccess && <p className="account-message is-success">{profileSuccess}</p>}
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
        <header className="account-panel-header">
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
            {pwError && <p className="account-message is-error">{pwError}</p>}
            {pwSuccess && <p className="account-message is-success">{pwSuccess}</p>}
            <div className="actions">
              <DashboardButton type="submit" variant="primary" loading={changePasswordMutation.isPending}>
                {changePasswordMutation.isPending ? "Saving..." : "Change password"}
              </DashboardButton>
            </div>
          </form>
        )}
      </section>

      <section className="panel profile-danger-zone" id="danger-zone">
        <header className="account-panel-header">
          <div>
            <h3 className="profile-danger-title">Danger zone</h3>
            <p>
              Permanently delete your account and all associated data. Transfer ownership of any workspace you own
              before deleting.
            </p>
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
