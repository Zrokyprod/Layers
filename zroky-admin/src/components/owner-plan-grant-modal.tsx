"use client";

import { AlertTriangle, BadgeDollarSign, CheckCircle2, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import {
  useCommitOwnerPlanGrant,
  useCreateOwnerPlanGrantChallenge,
  useOwnerPlanGrantAudit,
} from "@/lib/hooks";
import type {
  PlanGrantChallengeResponse,
  PlanGrantDurationKind,
  PlanGrantPlanCode,
} from "@/lib/owner-api";

const PLAN_OPTIONS: { value: PlanGrantPlanCode; label: string }[] = [
  { value: "free", label: "Free" },
  { value: "starter", label: "Starter" },
  { value: "pro", label: "Pro" },
];

const DURATION_OPTIONS: { value: PlanGrantDurationKind; label: string }[] = [
  { value: "permanent", label: "Permanent" },
  { value: "comp_30d", label: "Comp 30d" },
  { value: "comp_90d", label: "Comp 90d" },
];

interface OwnerPlanGrantModalProps {
  orgId: string;
  orgLabel?: string;
  onClose: () => void;
  onGranted?: (planCode: PlanGrantPlanCode) => void;
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function OwnerPlanGrantModal({
  orgId,
  orgLabel,
  onClose,
  onGranted,
}: OwnerPlanGrantModalProps) {
  const [targetPlanCode, setTargetPlanCode] = useState<PlanGrantPlanCode>("pro");
  const [durationKind, setDurationKind] = useState<PlanGrantDurationKind>("permanent");
  const [reason, setReason] = useState("");
  const [typedConfirmation, setTypedConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<PlanGrantChallengeResponse | null>(null);
  const [message, setMessage] = useState("");

  const challengeMutation = useCreateOwnerPlanGrantChallenge();
  const commitMutation = useCommitOwnerPlanGrant();
  const auditQuery = useOwnerPlanGrantAudit(orgId, 8);
  const recentGrants = auditQuery.data?.items ?? [];
  const busy = challengeMutation.isPending || commitMutation.isPending;
  const canCommit = Boolean(challenge && code.trim().length >= 6 && typedConfirmation.trim() && reason.trim());

  async function handleCreateChallenge() {
    setMessage("");
    setCode("");
    setChallenge(null);
    try {
      const next = await challengeMutation.mutateAsync({
        org_id: orgId,
        target_plan_code: targetPlanCode,
      });
      setChallenge(next);
      if (next.dev_code) {
        setCode(next.dev_code);
      }
    } catch (error: unknown) {
      setMessage(`Error: ${(error as Error).message}`);
    }
  }

  async function handleCommitGrant() {
    if (!challenge) return;
    setMessage("");
    try {
      const result = await commitMutation.mutateAsync({
        challenge_id: challenge.challenge_id,
        code: code.trim(),
        typed_confirmation: typedConfirmation.trim(),
        org_id: orgId,
        target_plan_code: targetPlanCode,
        reason: reason.trim(),
        duration_kind: durationKind,
      });
      setMessage(`Plan changed from ${result.previous_plan_code ?? "none"} to ${result.plan_code}.`);
      onGranted?.(result.plan_code);
    } catch (error: unknown) {
      setMessage(`Error: ${(error as Error).message}`);
    }
  }

  return (
    <div className="owner-modal-backdrop" role="presentation">
      <section className="owner-modal" role="dialog" aria-modal="true" aria-labelledby="owner-plan-grant-title">
        <header className="owner-modal-header">
          <div>
            <span className="owner-section-label">Owner plan override</span>
            <h3 id="owner-plan-grant-title">Change subscription</h3>
            <p>
              {orgLabel ?? "Tenant"} <code>{orgId}</code>
            </p>
          </div>
          <button className="btn btn-icon" type="button" onClick={onClose} aria-label="Close plan grant modal">
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="owner-modal-body">
          <div className="owner-plan-grant-warning">
            <AlertTriangle size={17} aria-hidden="true" />
            <span>This changes billing state and plan entitlements after OTP and exact target confirmation.</span>
          </div>

          {message && (
            <div className={`alert-strip ${message.startsWith("Error") ? "alert-strip-error" : ""}`}>
              {message}
            </div>
          )}

          <div className="owner-plan-grant-grid">
            <label className="field">
              <span className="field-label">Target plan</span>
              <select
                className="input"
                value={targetPlanCode}
                disabled={busy}
                onChange={(event) => {
                  setTargetPlanCode(event.target.value as PlanGrantPlanCode);
                  setChallenge(null);
                  setCode("");
                }}
              >
                {PLAN_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field-label">Duration</span>
              <select
                className="input"
                value={durationKind}
                disabled={busy}
                onChange={(event) => setDurationKind(event.target.value as PlanGrantDurationKind)}
              >
                {DURATION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="field">
            <span className="field-label">Reason</span>
            <textarea
              className="input owner-plan-grant-textarea"
              value={reason}
              disabled={busy}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Design partner override, billing correction, founder-approved comp..."
            />
          </label>

          <div className="owner-plan-grant-step">
            <div>
              <strong>1. Send verification code</strong>
              {challenge ? (
                <span>
                  Challenge active until {formatTimestamp(challenge.expires_at)} via {challenge.delivery}.
                </span>
              ) : (
                <span>Generates a single-use challenge for this tenant and plan.</span>
              )}
            </div>
            <button className="btn btn-soft" type="button" onClick={handleCreateChallenge} disabled={busy}>
              <ShieldCheck size={15} aria-hidden="true" />
              {challengeMutation.isPending ? "Sending..." : challenge ? "Resend code" : "Send code"}
            </button>
          </div>

          {challenge && (
            <div className="owner-plan-grant-confirm">
              {challenge.dev_code && (
                <div className="owner-plan-grant-dev-code">
                  <span>Local code</span>
                  <code>{challenge.dev_code}</code>
                </div>
              )}
              <label className="field">
                <span className="field-label">Verification code</span>
                <input
                  className="input"
                  inputMode="numeric"
                  maxLength={12}
                  value={code}
                  disabled={busy}
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
              <label className="field">
                <span className="field-label">Exact confirmation</span>
                <input
                  className="input"
                  value={typedConfirmation}
                  disabled={busy}
                  onChange={(event) => setTypedConfirmation(event.target.value)}
                  placeholder={orgId}
                />
              </label>
            </div>
          )}

          <div className="owner-plan-grant-history">
            <div className="panel-header">
              Recent grants
              <span className="panel-header-note">{auditQuery.isLoading ? "Loading" : `${recentGrants.length} shown`}</span>
            </div>
            {recentGrants.length === 0 && <p className="owner-panel-empty">No recent owner plan grants.</p>}
            {recentGrants.length > 0 && (
              <div className="owner-plan-grant-history-list">
                {recentGrants.map((item) => (
                  <div key={item.id} className="owner-plan-grant-history-row">
                    <div>
                      <strong>
                        {item.previous_plan_code ?? "none"} to {item.plan_code ?? "unknown"}
                      </strong>
                      <span>{item.reason ?? "No reason captured"}</span>
                    </div>
                    <time>{formatTimestamp(item.created_at)}</time>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <footer className="owner-modal-footer">
          <button className="btn btn-soft" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" type="button" onClick={handleCommitGrant} disabled={!canCommit || busy}>
            {commitMutation.isPending ? (
              "Applying..."
            ) : (
              <>
                <BadgeDollarSign size={15} aria-hidden="true" />
                Apply subscription change
              </>
            )}
          </button>
          {commitMutation.isSuccess && (
            <span className="owner-plan-grant-success">
              <CheckCircle2 size={15} aria-hidden="true" />
              Applied
            </span>
          )}
        </footer>
      </section>
    </div>
  );
}
