"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  LockKeyhole,
  RefreshCw,
  Save,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

import {
  getPilotPolicy,
  listRuntimePolicyApprovals,
  setRuntimePolicyKillSwitch,
  updatePilotPolicy,
  type PilotPolicyPayload,
  type RuntimePolicyDecisionResponse,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const DASH = "-";
const ACTIVE_GUARDRAIL_COUNT = 5;

function listToText(values: string[]): string {
  return values.join(", ");
}

function textToList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function statusTone(enabled: boolean): "tone-success" | "tone-warning" {
  return enabled ? "tone-success" : "tone-warning";
}

function policyStepClass(tone: "ready" | "warn" | "danger" | "neutral"): string {
  return `policy-proof-step is-${tone}`;
}

function formatUsd(value: number | null | undefined): string {
  if (value == null) return DASH;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value);
}

function toolsLabel(values: string[] | undefined, emptyLabel: string): string {
  if (!values || values.length === 0) return emptyLabel;
  return `${values.length} ${values.length === 1 ? "tool" : "tools"}`;
}

function decisionStatusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function decisionTone(item: RuntimePolicyDecisionResponse): "is-ready" | "is-warn" | "is-danger" {
  if (item.status === "allowed" || item.status === "approved") return "is-ready";
  if (item.status === "blocked" || item.status === "rejected") return "is-danger";
  return "is-warn";
}

function decisionTitle(item: RuntimePolicyDecisionResponse): string {
  return item.action_type || item.tool_name || item.role || "Runtime action";
}

function decisionSubtitle(item: RuntimePolicyDecisionResponse): string {
  return [item.agent_name, item.tool_name, item.call_id || item.trace_id].filter(Boolean).join(" - ") || "Runtime policy decision";
}

function decisionReason(item: RuntimePolicyDecisionResponse): string {
  return item.reasons[0] || (item.requires_approval ? "Human approval required." : "Policy decision captured.");
}

function policyReadiness(policy: PilotPolicyPayload | null): {
  label: string;
  helper: string;
  tone: "tone-danger" | "tone-success" | "tone-warning";
} {
  if (!policy) {
    return {
      label: "Unknown",
      helper: "Policy could not be loaded yet.",
      tone: "tone-warning",
    };
  }
  if (policy.kill_switch) {
    return {
      label: "Stopped",
      helper: "Kill switch is enabled. Autonomous actions should not proceed.",
      tone: "tone-danger",
    };
  }
  if (!policy.runtime_enabled) {
    return {
      label: "Ungated",
      helper: "Runtime policy checks are disabled for this project.",
      tone: "tone-warning",
    };
  }
  if (!policy.runtime_sensitive_actions_require_approval) {
    return {
      label: "Weak",
      helper: "Sensitive actions do not require approval.",
      tone: "tone-warning",
    };
  }
  return {
    label: "Controlled",
    helper: "Runtime gate is active and sensitive actions require approval.",
    tone: "tone-success",
  };
}

function policyVerdict({
  activeGuardrails,
  blockedActions,
  pendingApprovals,
  policy,
}: {
  activeGuardrails: number;
  blockedActions: number;
  pendingApprovals: number;
  policy: PilotPolicyPayload | null;
}): {
  badge: string;
  copy: string;
  title: string;
  tone: "danger" | "neutral" | "success" | "warning";
} {
  if (!policy) {
    return {
      badge: "Loading",
      copy: "Loading the saved runtime policy and latest decisions before showing the current action boundary.",
      title: "Policy status loading",
      tone: "neutral",
    };
  }
  if (policy.kill_switch) {
    return {
      badge: "Stopped",
      copy: "The kill switch is on. Autonomous actions should remain frozen until an operator reopens the project.",
      title: "Autonomy stopped",
      tone: "danger",
    };
  }
  if (!policy.runtime_enabled) {
    return {
      badge: "Ungated",
      copy: "Runtime checks are disabled, so agent actions can execute without the policy gate producing proof.",
      title: "Runtime gate disabled",
      tone: "danger",
    };
  }
  if (!policy.runtime_sensitive_actions_require_approval) {
    return {
      badge: "Approval gap",
      copy: "Sensitive actions are not forced through human approval, so high-impact tool calls can skip review.",
      title: "Approval gap open",
      tone: "warning",
    };
  }
  if (activeGuardrails < ACTIVE_GUARDRAIL_COUNT) {
    return {
      badge: "Incomplete",
      copy: "The runtime gate is active, but one or more high-stakes blockers are not enforcing the boundary.",
      title: "Guardrails incomplete",
      tone: "warning",
    };
  }
  if (pendingApprovals > 0) {
    return {
      badge: "Review",
      copy: "The policy gate is working and has paused sensitive actions for human approval before execution.",
      title: "Human review waiting",
      tone: "warning",
    };
  }
  if (blockedActions > 0) {
    return {
      badge: "Blocked",
      copy: "The runtime gate has blocked risky actions and kept a decision trail for audit and evidence review.",
      title: "Policy caught risky action",
      tone: "success",
    };
  }
  return {
    badge: "Controlled",
    copy: "Runtime checks, approval holds, and high-stakes blockers are active before autonomous actions continue.",
    title: "Runtime policy enforced",
    tone: "success",
  };
}

function PolicyMandateContract() {
  const rules = [
    {
      label: "Mandate",
      title: "Define what agents may attempt",
      body: "Allowed tools and sensitive tools draw the action boundary before runtime execution.",
      tone: "neutral",
    },
    {
      label: "Risk limits",
      title: "Cap blast radius",
      body: "Tool-call count, retries, and cost limits stop runaway autonomous behavior.",
      tone: "warning",
    },
    {
      label: "Approval",
      title: "Hold sensitive actions",
      body: "Money, customer, message, delete, or external side effects should pause before commit.",
      tone: "success",
    },
    {
      label: "Fail closed",
      title: "Block unsafe paths",
      body: "PII leakage, prompt-injected external actions, and kill-switch events stop execution.",
      tone: "danger",
    },
  ];

  return (
    <section className="policy-mandate-contract" aria-label="Policy mandate contract">
      <div className="policy-mandate-contract-head">
        <span className="eyebrow">Mandate contract</span>
        <h2>Policies define what an agent may attempt before any risky tool call runs.</h2>
        <p>
          Approvals decide exceptions. Outcomes verify the real result. Evidence Packs export the proof trail.
        </p>
      </div>
      <div className="policy-mandate-contract-grid">
        {rules.map((rule) => (
          <article key={rule.label} data-tone={rule.tone}>
            <span className="policy-contract-tag">{rule.label}</span>
            <strong>{rule.title}</strong>
            <small>{rule.body}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="settings-toggle-row">
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

export default function PoliciesPage() {
  const queryClient = useQueryClient();
  const [policy, setPolicy] = useState<PilotPolicyPayload | null>(null);
  const [allowedTools, setAllowedTools] = useState("");
  const [sensitiveTools, setSensitiveTools] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const policyQuery = useQuery({
    queryKey: ["pilot-policy"],
    queryFn: ({ signal }) => getPilotPolicy(signal),
    staleTime: 30_000,
    retry: false,
  });

  const approvalsQuery = useQuery({
    queryKey: ["runtime-policy", "approvals", "all"],
    queryFn: ({ signal }) => listRuntimePolicyApprovals("all", signal),
    staleTime: 10_000,
    refetchInterval: 15_000,
    retry: false,
  });

  const savePolicyMutation = useMutation({
    mutationFn: updatePilotPolicy,
    onSuccess: (response) => {
      setPolicy(response.policy);
      setAllowedTools(listToText(response.policy.runtime_allowed_tools));
      setSensitiveTools(listToText(response.policy.runtime_sensitive_tools));
      setMessage("Policy saved.");
      queryClient.setQueryData(["pilot-policy"], response);
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Policy save failed.");
    },
  });

  const killSwitchMutation = useMutation({
    mutationFn: setRuntimePolicyKillSwitch,
    onSuccess: () => {
      setMessage("Kill switch enabled.");
      void queryClient.invalidateQueries({ queryKey: ["pilot-policy"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Kill switch update failed.");
    },
  });

  useEffect(() => {
    if (!policyQuery.data?.policy) return;
    setPolicy(policyQuery.data.policy);
    setAllowedTools(listToText(policyQuery.data.policy.runtime_allowed_tools));
    setSensitiveTools(listToText(policyQuery.data.policy.runtime_sensitive_tools));
  }, [policyQuery.data]);

  const readiness = useMemo(() => policyReadiness(policy), [policy]);
  const approvals = approvalsQuery.data?.items ?? [];
  const pendingApprovals = approvals.filter((item) => item.status === "pending_approval").length;
  const blockedActions = approvals.filter((item) => item.status === "blocked" || item.status === "rejected").length;
  const approvedOrAllowedActions = approvals.filter((item) => item.status === "approved" || item.status === "allowed").length;
  const sensitiveToolCount = policy?.runtime_sensitive_tools.length ?? 0;
  const allowedToolCount = policy?.runtime_allowed_tools.length ?? 0;
  const activeGuardrails = policy
    ? [
        policy.runtime_sensitive_actions_require_approval,
        policy.runtime_block_pii_leak,
        policy.runtime_block_prompt_injected_external_action,
        policy.runtime_production_deploys_require_approval,
        policy.runtime_changed_recipient_deny,
      ].filter(Boolean).length
    : 0;
  const runtimeEnabled = Boolean(policy?.runtime_enabled);
  const killSwitchEnabled = Boolean(policy?.kill_switch);
  const latestDecisions = approvals.slice(0, 5);
  const heroVerdict = policyVerdict({
    activeGuardrails,
    blockedActions,
    pendingApprovals,
    policy,
  });

  function updatePolicyField<Key extends keyof PilotPolicyPayload>(key: Key, value: PilotPolicyPayload[Key]) {
    setPolicy((current) => (current ? { ...current, [key]: value } : current));
  }

  function savePolicy() {
    if (!policy) return;
    setMessage(null);
    savePolicyMutation.mutate({
      ...policy,
      runtime_allowed_tools: textToList(allowedTools),
      runtime_sensitive_tools: textToList(sensitiveTools),
    });
  }

  return (
    <div className="dashboard-page policies-page">
      <section className="page-header policy-command-hero" data-tone={heroVerdict.tone}>
        <div className="policy-hero-copy">
          <span className="eyebrow">Runtime gate</span>
          <h1>{heroVerdict.title}</h1>
          <p>{heroVerdict.copy}</p>
        </div>
        <div className="policy-hero-side">
          <div className="policy-verdict-card" aria-label="Runtime policy verdict">
            <span>{heroVerdict.badge}</span>
            <strong>{activeGuardrails}/{ACTIVE_GUARDRAIL_COUNT}</strong>
            <small>guardrails active</small>
          </div>
          <div className="policy-flow-rail" aria-label="Runtime policy proof chain">
            <span>Boundary</span>
            <strong>Gate</strong>
            <span>Hold</span>
            <span>Evidence</span>
          </div>
          <div className="page-actions">
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => {
                setMessage(null);
                void Promise.all([policyQuery.refetch(), approvalsQuery.refetch()]);
              }}
              disabled={policyQuery.isFetching || approvalsQuery.isFetching}
            >
              <RefreshCw size={16} />
              Refresh
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              disabled={killSwitchMutation.isPending || policy?.kill_switch === true}
              onClick={() => killSwitchMutation.mutate(true)}
            >
              <ShieldAlert size={16} />
              Kill switch
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={!policy || savePolicyMutation.isPending}
              onClick={savePolicy}
            >
              <Save size={16} />
              {savePolicyMutation.isPending ? "Saving..." : "Save policy"}
            </button>
          </div>
        </div>
      </section>

      {message ? <div className="notice" role="status">{message}</div> : null}

      <section className="metric-grid compact policy-metric-grid" aria-label="Policy safety summary">
        <article className={`metric-card policy-metric-card ${readiness.tone}`}>
          <CheckCircle2 size={18} />
          <span>Scale safety</span>
          <strong>{readiness.label}</strong>
          <small>{readiness.helper}</small>
        </article>
        <article className={`metric-card policy-metric-card ${statusTone(Boolean(policy?.runtime_enabled))}`}>
          <SlidersHorizontal size={18} />
          <span>Runtime gate</span>
          <strong>{policy?.runtime_enabled ? "Enabled" : "Disabled"}</strong>
          <small>Applies limits before risky autonomous actions continue.</small>
        </article>
        <article className="metric-card policy-metric-card tone-warning">
          <Clock3 size={18} />
          <span>Pending approvals</span>
          <strong>{approvalsQuery.isLoading ? DASH : pendingApprovals}</strong>
          <small>Approval queue items waiting on a human decision.</small>
        </article>
        <article className="metric-card policy-metric-card tone-danger">
          <AlertTriangle size={18} />
          <span>Blocked actions</span>
          <strong>{approvalsQuery.isLoading ? DASH : blockedActions}</strong>
          <small>Rejected or blocked policy decisions visible in the audit trail.</small>
        </article>
      </section>

      <PolicyMandateContract />

      <section className="policy-proof-strip" aria-label="Mandate proof flow">
        <article className={policyStepClass(killSwitchEnabled ? "danger" : runtimeEnabled ? "ready" : "warn")}>
          <span>01</span>
          <strong>Mandate boundary</strong>
          <small>
            {killSwitchEnabled
              ? "Frozen by kill switch."
              : runtimeEnabled
                ? `${allowedToolCount > 0 ? `${allowedToolCount} allowed tools` : "Open non-sensitive surface"}, ${sensitiveToolCount} sensitive tools.`
                : "Runtime gate is disabled."}
          </small>
        </article>
        <article className={policyStepClass(activeGuardrails === ACTIVE_GUARDRAIL_COUNT ? "ready" : activeGuardrails > 0 ? "warn" : "danger")}>
          <span>02</span>
          <strong>Pre-action gate</strong>
          <small>{activeGuardrails}/{ACTIVE_GUARDRAIL_COUNT} high-stakes guardrails enabled.</small>
        </article>
        <article className={policyStepClass(pendingApprovals > 0 ? "warn" : "ready")}>
          <span>03</span>
          <strong>Human hold</strong>
          <small>{pendingApprovals} pending approval{pendingApprovals === 1 ? "" : "s"} before execution.</small>
        </article>
        <article className={policyStepClass(blockedActions > 0 ? "danger" : latestDecisions.length > 0 ? "ready" : "neutral")}>
          <span>04</span>
          <strong>Evidence trail</strong>
          <small>{latestDecisions.length > 0 ? `${latestDecisions.length} recent decisions loaded.` : "No runtime decisions loaded yet."}</small>
        </article>
      </section>

      {policyQuery.isLoading ? <div className="empty">Loading runtime policy...</div> : null}
      {policyQuery.isError ? (
        <div className="empty error">
          {policyQuery.error instanceof Error ? policyQuery.error.message : "Policy could not load."}
        </div>
      ) : null}

      {policy ? (
        <>
          <section className="policy-boundary-grid" aria-label="Current mandate boundary">
            <article className="policy-boundary-card">
              <span>Allowed surface</span>
              <strong>{toolsLabel(policy.runtime_allowed_tools, "Open non-sensitive tools")}</strong>
              <p>{policy.runtime_allowed_tools.length > 0 ? policy.runtime_allowed_tools.join(", ") : "Any non-sensitive tool may run inside the runtime limits."}</p>
            </article>
            <article className="policy-boundary-card">
              <span>Hold conditions</span>
              <strong>{toolsLabel(policy.runtime_sensitive_tools, "No sensitive tools listed")}</strong>
              <p>
                {policy.runtime_sensitive_actions_require_approval
                  ? `Sensitive actions hold for ${policy.runtime_approval_ttl_minutes} minutes.`
                  : "Sensitive actions do not currently force human approval."}
              </p>
            </article>
            <article className="policy-boundary-card">
              <span>Execution limits</span>
              <strong>{formatUsd(policy.runtime_max_cost_usd)} per action</strong>
              <p>{policy.runtime_max_tool_calls} tool calls, {policy.runtime_max_retries} retries, then the action must stop.</p>
            </article>
            <article className="policy-boundary-card">
              <span>Latest decisions</span>
              <strong>{approvedOrAllowedActions} allowed, {blockedActions} blocked</strong>
              <p>{pendingApprovals} waiting for review in the runtime approval queue.</p>
            </article>
          </section>

          <section className="policy-decision-panel" aria-label="Latest runtime decisions">
            <header className="panel-header">
              <div>
                <h3>Latest runtime decisions</h3>
                <p>Recent allow, hold, and block events generated when SDK or Gateway called the runtime gate.</p>
              </div>
              <Link href="/approvals" className="btn btn-soft btn-sm">Open approvals</Link>
            </header>
            {latestDecisions.length > 0 ? (
              <div className="policy-decision-list">
                {latestDecisions.map((item) => (
                  <article key={item.id} className={`policy-decision-row ${decisionTone(item)}`}>
                    <div>
                      <strong>{decisionTitle(item)}</strong>
                      <span>{decisionSubtitle(item)}</span>
                    </div>
                    <p>{decisionReason(item)}</p>
                    <span className="policy-decision-status">{decisionStatusLabel(item.status)}</span>
                  </article>
                ))}
              </div>
            ) : (
              <div className="policy-empty-state">
                Runtime decisions will appear after an agent calls the policy gate.
              </div>
            )}
          </section>

        <section className="settings-integration-grid policy-editor-grid">
          <article className="panel settings-control-panel">
            <header className="panel-header">
              <div>
                <h3>Runtime controls</h3>
                <p>Limits and blockers that prevent autonomous agents from scaling unsafe behavior.</p>
              </div>
              <span className={policy.kill_switch ? "pill pill-red" : "pill pill-green"}>
                {policy.kill_switch ? "Kill switch on" : "Live"}
              </span>
            </header>

            <div className="settings-form-grid">
              <ToggleRow
                label="Runtime policy gate"
                description="Evaluate risky actions before execution."
                checked={policy.runtime_enabled}
                onChange={(checked) => updatePolicyField("runtime_enabled", checked)}
              />
              <ToggleRow
                label="Kill switch"
                description="Stop autonomous actions until the project is manually reopened."
                checked={policy.kill_switch}
                onChange={(checked) => updatePolicyField("kill_switch", checked)}
              />
              <ToggleRow
                label="Sensitive actions require approval"
                description="Pause payment, refund, delete, email, transfer, and similar actions."
                checked={policy.runtime_sensitive_actions_require_approval}
                onChange={(checked) => updatePolicyField("runtime_sensitive_actions_require_approval", checked)}
              />
              <ToggleRow
                label="Block PII leak"
                description="Block policy decisions that indicate PII could leave the approved path."
                checked={policy.runtime_block_pii_leak}
                onChange={(checked) => updatePolicyField("runtime_block_pii_leak", checked)}
              />
              <ToggleRow
                label="Block prompt-injected external action"
                description="Stop external side effects triggered by suspected prompt injection."
                checked={policy.runtime_block_prompt_injected_external_action}
                onChange={(checked) => updatePolicyField("runtime_block_prompt_injected_external_action", checked)}
              />
              <ToggleRow
                label="Production deploy approval"
                description="Hold production deploy actions until a human approves the exact intent."
                checked={policy.runtime_production_deploys_require_approval}
                onChange={(checked) => updatePolicyField("runtime_production_deploys_require_approval", checked)}
              />
              <ToggleRow
                label="Changed recipient deny"
                description="Deny customer-visible messages when the recipient changes after intent creation."
                checked={policy.runtime_changed_recipient_deny}
                onChange={(checked) => updatePolicyField("runtime_changed_recipient_deny", checked)}
              />
            </div>
          </article>

          <article className="panel settings-control-panel">
            <header className="panel-header">
              <div>
                <h3>Budgets and limits</h3>
                <p>Hard limits for tool use, retries, cost, and approval expiry.</p>
              </div>
              <LockKeyhole aria-hidden="true" />
            </header>

            <div className="settings-form-grid">
              <label>
                <span>Max tool calls</span>
                <input
                  type="number"
                  min={0}
                  value={policy.runtime_max_tool_calls}
                  onChange={(event) => updatePolicyField("runtime_max_tool_calls", Number(event.target.value))}
                />
              </label>
              <label>
                <span>Max retries</span>
                <input
                  type="number"
                  min={0}
                  value={policy.runtime_max_retries}
                  onChange={(event) => updatePolicyField("runtime_max_retries", Number(event.target.value))}
                />
              </label>
              <label>
                <span>Max cost per action (USD)</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={policy.runtime_max_cost_usd}
                  onChange={(event) => updatePolicyField("runtime_max_cost_usd", Number(event.target.value))}
                />
              </label>
              <label>
                <span>Approval TTL minutes</span>
                <input
                  type="number"
                  min={1}
                  value={policy.runtime_approval_ttl_minutes}
                  onChange={(event) => updatePolicyField("runtime_approval_ttl_minutes", Number(event.target.value))}
                />
              </label>
              <label>
                <span>Approval threshold (USD)</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={policy.runtime_amount_approval_threshold_usd ?? ""}
                  onChange={(event) =>
                    updatePolicyField(
                      "runtime_amount_approval_threshold_usd",
                      event.target.value === "" ? null : Number(event.target.value),
                    )
                  }
                />
              </label>
              <label>
                <span>Dual approval threshold (USD)</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={policy.runtime_amount_deny_threshold_usd ?? ""}
                  onChange={(event) =>
                    updatePolicyField(
                      "runtime_amount_deny_threshold_usd",
                      event.target.value === "" ? null : Number(event.target.value),
                    )
                  }
                />
              </label>
            </div>
          </article>

          <article className="panel settings-control-panel">
            <header className="panel-header">
              <div>
                <h3>Tool policy</h3>
                <p>Allowed tools narrow execution. Sensitive tools trigger the approval path.</p>
              </div>
            </header>

            <div className="settings-form-grid">
              <label>
                <span>Allowed tools</span>
                <textarea
                  value={allowedTools}
                  onChange={(event) => setAllowedTools(event.target.value)}
                  placeholder="Leave empty to allow any non-sensitive tool, or comma-separate tool names."
                />
              </label>
              <label>
                <span>Sensitive tools</span>
                <textarea
                  value={sensitiveTools}
                  onChange={(event) => setSensitiveTools(event.target.value)}
                  placeholder="payment, refund, delete, email"
                />
              </label>
            </div>
          </article>

          <article className="panel settings-control-panel">
            <header className="panel-header">
              <div>
                <h3>Evidence path</h3>
                <p>Policy hits should be visible in traces and human approvals before damage.</p>
              </div>
            </header>
            <div className="list">
              <div className="list-row">
                <div className="list-main">
                  <strong>Last updated</strong>
                  <span>{formatDateTime(policyQuery.data?.updated_at)}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Updated by</strong>
                  <span>{policyQuery.data?.updated_by ?? DASH}</span>
                </div>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Approval queue</strong>
                  <span>{pendingApprovals} pending policy decision{pendingApprovals === 1 ? "" : "s"}</span>
                </div>
                <Link href="/approvals" className="btn btn-soft btn-sm">Open approvals</Link>
              </div>
              <div className="list-row">
                <div className="list-main">
                  <strong>Trace evidence</strong>
                  <span>Policy decisions are captured as trace evidence when SDK/Gateway calls the runtime gate.</span>
                </div>
                <Link href="/evidence" className="btn btn-soft btn-sm">Open evidence</Link>
              </div>
            </div>
          </article>
        </section>
        </>
      ) : null}
    </div>
  );
}
