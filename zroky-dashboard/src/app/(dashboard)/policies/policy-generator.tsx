"use client";

import { useMemo, useState } from "react";
import {
  DatabaseZap,
  Mail,
  Rocket,
  ShieldCheck,
  WalletCards,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import type { PilotPolicyPayload } from "@/lib/api";

export type PolicyGeneratorMode = "review_first" | "balanced" | "higher_autonomy";
export type PolicyProtectionArea = "money" | "records" | "messages" | "production";

type ModeOption = {
  id: PolicyGeneratorMode;
  label: string;
  detail: string;
  approvalThreshold: number;
  dualApprovalThreshold: number;
  maxToolCalls: number;
  maxRetries: number;
  approvalTtlMinutes: number;
};

const MODE_OPTIONS: ModeOption[] = [
  {
    id: "review_first",
    label: "Review first",
    detail: "Hold every selected high-impact action for a person.",
    approvalThreshold: 0,
    dualApprovalThreshold: 500,
    maxToolCalls: 6,
    maxRetries: 1,
    approvalTtlMinutes: 15,
  },
  {
    id: "balanced",
    label: "Balanced",
    detail: "Allow routine work and hold meaningful risk.",
    approvalThreshold: 500,
    dualApprovalThreshold: 5_000,
    maxToolCalls: 12,
    maxRetries: 2,
    approvalTtlMinutes: 30,
  },
  {
    id: "higher_autonomy",
    label: "Higher autonomy",
    detail: "Use wider limits while keeping hard blockers on.",
    approvalThreshold: 2_000,
    dualApprovalThreshold: 10_000,
    maxToolCalls: 20,
    maxRetries: 3,
    approvalTtlMinutes: 60,
  },
];

const PROTECTION_AREAS: Array<{
  id: PolicyProtectionArea;
  label: string;
  detail: string;
  icon: typeof WalletCards;
}> = [
  { id: "money", label: "Money movement", detail: "Payments, refunds, transfers and payouts", icon: WalletCards },
  { id: "records", label: "Customer and data changes", detail: "Deletes and customer or database updates", icon: DatabaseZap },
  { id: "messages", label: "External messages", detail: "Email and other customer-facing sends", icon: Mail },
  { id: "production", label: "Production changes", detail: "Deployments and production execution", icon: Rocket },
];

const MANAGED_SENSITIVE_TOOLS = new Set([
  "payment",
  "charge",
  "refund",
  "transfer",
  "payout",
  "delete",
  "customer_record_update",
  "database_record_update",
  "email",
  "send_email",
  "deploy_change",
]);

function selectedMode(mode: PolicyGeneratorMode): ModeOption {
  return MODE_OPTIONS.find((item) => item.id === mode) ?? MODE_OPTIONS[1];
}

export function generatePolicyFromAnswers(
  current: PilotPolicyPayload,
  mode: PolicyGeneratorMode,
  areas: PolicyProtectionArea[],
): PilotPolicyPayload {
  const profile = selectedMode(mode);
  const selected = new Set(areas);
  const customSensitiveTools = current.runtime_sensitive_tools.filter(
    (tool) => !MANAGED_SENSITIVE_TOOLS.has(tool.toLowerCase()),
  );
  const sensitiveTools = new Set(customSensitiveTools);

  if (selected.has("money")) {
    if (mode === "review_first") {
      ["payment", "charge", "refund", "transfer", "payout"].forEach((tool) => sensitiveTools.add(tool));
    } else {
      // Amount-aware payment/refund/transfer calls use the generated thresholds.
      ["charge", "payout"].forEach((tool) => sensitiveTools.add(tool));
    }
  }
  if (selected.has("records")) {
    ["delete", "customer_record_update", "database_record_update"].forEach((tool) => sensitiveTools.add(tool));
  }
  if (selected.has("messages")) {
    ["email", "send_email"].forEach((tool) => sensitiveTools.add(tool));
  }
  if (selected.has("production")) {
    // A non-empty list avoids falling back to the backend's broad default keyword list.
    sensitiveTools.add("deploy_change");
  }

  return {
    ...current,
    runtime_enabled: true,
    runtime_max_tool_calls: profile.maxToolCalls,
    runtime_max_retries: profile.maxRetries,
    runtime_sensitive_tools: [...sensitiveTools],
    runtime_sensitive_actions_require_approval: true,
    runtime_block_pii_leak: true,
    runtime_block_prompt_injected_external_action: true,
    runtime_approval_ttl_minutes: profile.approvalTtlMinutes,
    runtime_amount_approval_threshold_usd: selected.has("money") ? profile.approvalThreshold : null,
    runtime_amount_deny_threshold_usd: selected.has("money") ? profile.dualApprovalThreshold : null,
    runtime_production_deploys_require_approval: selected.has("production"),
    runtime_changed_recipient_deny: selected.has("messages"),
    runtime_sequence_risk_enabled: true,
  };
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function generatedSummary(mode: PolicyGeneratorMode, areas: PolicyProtectionArea[]): string[] {
  const profile = selectedMode(mode);
  const selected = new Set(areas);
  const summary: string[] = [];

  if (selected.has("money")) {
    summary.push(
      mode === "review_first"
        ? `Money movement waits for approval; above ${formatMoney(profile.dualApprovalThreshold)} needs two approvals.`
        : `Money movement above ${formatMoney(profile.approvalThreshold)} waits; above ${formatMoney(profile.dualApprovalThreshold)} needs two approvals.`,
    );
  }
  if (selected.has("records")) summary.push("Customer deletes and record changes wait for approval.");
  if (selected.has("messages")) summary.push("External messages wait for approval; changed recipients are denied.");
  if (selected.has("production")) summary.push("Production deployments wait for approval.");
  summary.push("PII leaks, prompt-injected side effects and risky action sequences are blocked or held.");
  return summary;
}

export function PolicyGenerator({
  disabled,
  policy,
  saving,
  onApply,
}: {
  disabled: boolean;
  policy: PilotPolicyPayload;
  saving: boolean;
  onApply: (policy: PilotPolicyPayload) => void;
}) {
  const [mode, setMode] = useState<PolicyGeneratorMode>("balanced");
  const [areas, setAreas] = useState<PolicyProtectionArea[]>(["money", "records", "messages", "production"]);
  const generated = useMemo(() => generatePolicyFromAnswers(policy, mode, areas), [areas, mode, policy]);
  const summary = useMemo(() => generatedSummary(mode, areas), [areas, mode]);

  function toggleArea(area: PolicyProtectionArea) {
    setAreas((current) => current.includes(area) ? current.filter((item) => item !== area) : [...current, area]);
  }

  return (
    <section className="panel policy-generator" aria-labelledby="policy-generator-title">
      <header className="policy-generator-header">
        <div>
          <span className="dashboard-eyebrow">Guided policy generator</span>
          <h2 id="policy-generator-title">Set the control level, not every field</h2>
          <p>Choose what the agent can affect. Zroky generates the enforced runtime policy and keeps advanced fields editable.</p>
        </div>
        <span className="policy-generator-step">2 choices</span>
      </header>

      <div className="policy-generator-question">
        <div className="policy-generator-question-copy">
          <span>1</span>
          <div>
            <strong>How much autonomy should agents have?</strong>
            <small>Balanced is recommended for a live project.</small>
          </div>
        </div>
        <div className="policy-mode-options" role="group" aria-label="Agent autonomy level">
          {MODE_OPTIONS.map((option) => (
            <button
              aria-pressed={mode === option.id}
              className="policy-choice"
              data-selected={mode === option.id}
              key={option.id}
              onClick={() => setMode(option.id)}
              type="button"
            >
              <strong>{option.label}{option.id === "balanced" ? " (Recommended)" : ""}</strong>
              <span>{option.detail}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="policy-generator-question">
        <div className="policy-generator-question-copy">
          <span>2</span>
          <div>
            <strong>What can create real-world impact?</strong>
            <small>Select every area this project uses.</small>
          </div>
        </div>
        <div className="policy-area-options" role="group" aria-label="Protected action areas">
          {PROTECTION_AREAS.map((area) => {
            const Icon = area.icon;
            const selected = areas.includes(area.id);
            return (
              <button
                aria-pressed={selected}
                className="policy-area-choice"
                data-selected={selected}
                key={area.id}
                onClick={() => toggleArea(area.id)}
                type="button"
              >
                <Icon aria-hidden="true" size={18} />
                <span>
                  <strong>{area.label}</strong>
                  <small>{area.detail}</small>
                </span>
                <span className="policy-area-check" aria-hidden="true">{selected ? "On" : "Off"}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="policy-generated-result" aria-live="polite">
        <div className="policy-generated-title">
          <ShieldCheck aria-hidden="true" size={20} />
          <div>
            <strong>Generated policy</strong>
            <span>{selectedMode(mode).label} / {areas.length} protected area{areas.length === 1 ? "" : "s"}</span>
          </div>
        </div>
        <ul>
          {summary.map((item) => <li key={item}>{item}</li>)}
        </ul>
        <DashboardButton
          disabled={disabled || areas.length === 0}
          icon={<ShieldCheck size={16} />}
          loading={saving}
          onClick={() => onApply(generated)}
          variant="primary"
        >
          Apply generated policy
        </DashboardButton>
        {areas.length === 0 ? <small className="policy-generator-error">Select at least one protected area.</small> : null}
      </div>
    </section>
  );
}
