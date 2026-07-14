"use client";

import { useState } from "react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import { StatusPill } from "@/components/status-pill";
import { statusLabel } from "@/lib/action-status";
import type {
  OutcomeMismatchResolutionCode,
  OutcomeMismatchResponseView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export type OutcomeMismatchCaseNotice = {
  caseId: string;
  text: string;
  tone: "danger" | "success";
};

const RESOLUTION_OPTIONS: Array<{ id: OutcomeMismatchResolutionCode; label: string }> = [
  { id: "confirmed_mismatch", label: "Confirmed mismatch" },
  { id: "expected_change", label: "Expected source change" },
  { id: "false_positive", label: "False positive" },
  { id: "unresolved", label: "Close as unresolved" },
];

function remediationBoundary(responseCase: OutcomeMismatchResponseView): string {
  const value = responseCase.remediation.safety_boundary;
  return typeof value === "string" && value.trim()
    ? value
    : "Any correction must run as a new protected action with its own approval and receipt.";
}

export function MismatchCasePanel({
  busy,
  canAcknowledge,
  canResolve,
  notice,
  onAcknowledge,
  onResolve,
  responseCase,
}: {
  busy: boolean;
  canAcknowledge: boolean;
  canResolve: boolean;
  notice: OutcomeMismatchCaseNotice | null;
  onAcknowledge: (responseCase: OutcomeMismatchResponseView) => void;
  onResolve: (
    responseCase: OutcomeMismatchResponseView,
    resolutionCode: OutcomeMismatchResolutionCode,
    resolutionNote: string,
  ) => void;
  responseCase: OutcomeMismatchResponseView | null;
}) {
  const [resolutionCode, setResolutionCode] = useState<OutcomeMismatchResolutionCode>("confirmed_mismatch");
  const [resolutionNote, setResolutionNote] = useState("");

  if (!responseCase) {
    return (
      <section className="outcomes-case-panel" data-tone="warning" aria-label="Mismatch response case">
        <div>
          <span className="dashboard-eyebrow">Response case</span>
          <strong>Case is not available yet</strong>
          <p>Refresh once the mismatch alert and operator case finish linking to this proof check.</p>
        </div>
      </section>
    );
  }

  const resolved = responseCase.status === "RESOLVED";
  const acknowledged = responseCase.status === "ACKNOWLEDGED";
  const caseNotice = notice?.caseId === responseCase.id ? notice : null;

  return (
    <section
      className="outcomes-case-panel"
      data-tone={resolved ? "success" : acknowledged ? "warning" : "danger"}
      aria-label="Mismatch response case"
    >
      <div className="outcomes-case-head">
        <div>
          <span className="dashboard-eyebrow">Response case</span>
          <strong>{resolved ? "Investigation closed" : acknowledged ? "Investigation owned" : "Needs an operator"}</strong>
        </div>
        <StatusPill
          label={responseCase.status.toLowerCase()}
          tone={resolved ? "success" : acknowledged ? "warning" : "danger"}
          value={responseCase.status.toLowerCase()}
        />
      </div>

      <p>{remediationBoundary(responseCase)}</p>

      {resolved ? (
        <dl className="outcomes-case-resolution">
          <div>
            <dt>Resolution</dt>
            <dd>{statusLabel(responseCase.resolution_code ?? "resolved")}</dd>
          </div>
          <div>
            <dt>Owner note</dt>
            <dd>{responseCase.resolution_note?.trim() || "No resolution note supplied."}</dd>
          </div>
          <div>
            <dt>Resolved</dt>
            <dd>{formatDateTime(responseCase.resolved_at)}</dd>
          </div>
        </dl>
      ) : (
        <div className="outcomes-case-actions">
          {canAcknowledge ? (
            <DashboardButtonLink
              href={`/actions?correction_case=${encodeURIComponent(responseCase.id)}`}
              size="sm"
              variant="primary"
            >
              Create corrective action
            </DashboardButtonLink>
          ) : null}
          {responseCase.status === "OPEN" ? (
            <DashboardButton
              disabled={busy || !canAcknowledge}
              loading={busy}
              onClick={() => onAcknowledge(responseCase)}
              size="sm"
              variant="soft"
            >
              Acknowledge case
            </DashboardButton>
          ) : null}
          <label>
            <span>Owner resolution</span>
            <select
              disabled={!canResolve}
              value={resolutionCode}
              onChange={(event) => setResolutionCode(event.target.value as OutcomeMismatchResolutionCode)}
            >
              {RESOLUTION_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Resolution note</span>
            <textarea
              disabled={!canResolve}
              value={resolutionNote}
              onChange={(event) => setResolutionNote(event.target.value)}
              placeholder="What was confirmed and what happens next?"
              rows={3}
            />
          </label>
          <DashboardButton
            disabled={busy || !canResolve || resolutionNote.trim().length < 3}
            loading={busy}
            onClick={() => onResolve(responseCase, resolutionCode, resolutionNote.trim())}
            size="sm"
            variant="primary"
          >
            Resolve case
          </DashboardButton>
          <small>
            {canResolve
              ? "Closing a case never changes the source system."
              : canAcknowledge
                ? "Your role can acknowledge this case; a workspace owner must resolve it."
                : "Viewer access is read-only. A member can acknowledge and an owner can resolve."}
          </small>
        </div>
      )}
      {caseNotice ? <small className="outcomes-case-notice" data-tone={caseNotice.tone}>{caseNotice.text}</small> : null}
    </section>
  );
}
