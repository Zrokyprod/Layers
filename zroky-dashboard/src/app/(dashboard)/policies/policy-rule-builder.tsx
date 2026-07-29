"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Ban,
  Check,
  Pencil,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  UserCheck,
  Users,
  SlidersHorizontal,
} from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import type {
  AgentProfileResponse,
  PilotPolicyPayload,
  RuntimePolicyRulePayload,
  RuntimePolicyRuleResponse,
} from "@/lib/api";
import { POLICY_ACTION_OPTIONS, actionLabel, describePolicyPatch } from "@/lib/policy-rules-view";

type RuleOutcome = NonNullable<PilotPolicyPayload["runtime_action_decision"]>;

export type PolicyRuleDraft = {
  agentId: string;
  actionChoice: string;
  customAction: string;
  environmentChoice: string;
  customEnvironment: string;
  outcome: RuleOutcome;
  description: string;
  maxToolCalls: string;
  maxRetries: string;
  maxCost: string;
  approvalTtl: string;
  approvalThreshold: string;
  dualApprovalThreshold: string;
};

type RuleTemplate = {
  id: string;
  label: string;
  action: string;
  environment: string;
  outcome: RuleOutcome;
  description: string;
};

const CUSTOM = "__custom__";
const ANY = "";

export const POLICY_RULE_TEMPLATES: RuleTemplate[] = [
  {
    id: "sales",
    label: "Sales / outreach",
    action: "email_send",
    environment: ANY,
    outcome: "require_approval",
    description: "Review customer-facing messages before they are sent.",
  },
  {
    id: "support",
    label: "Support operations",
    action: "ticket_close",
    environment: ANY,
    outcome: "require_approval",
    description: "Review ticket closure before the support agent completes it.",
  },
  {
    id: "release",
    label: "Coding / release",
    action: "deploy_change",
    environment: "production",
    outcome: "require_approval",
    description: "Review production deployments while leaving non-production work unchanged.",
  },
  {
    id: "finance",
    label: "Finance / spend",
    action: "invoice_spend_approval",
    environment: ANY,
    outcome: "require_two_approvals",
    description: "Require two people to approve a spend commitment.",
  },
  {
    id: "data",
    label: "CRM / data",
    action: "customer_record_update",
    environment: ANY,
    outcome: "require_approval",
    description: "Review customer-record changes before they reach the system of record.",
  },
  {
    id: "custom",
    label: "Custom agent action",
    action: CUSTOM,
    environment: ANY,
    outcome: "require_approval",
    description: "",
  },
];

const OUTCOME_OPTIONS: Array<{
  id: RuleOutcome;
  label: string;
  detail: string;
  icon: typeof Check;
}> = [
  { id: "allow", label: "Allow", detail: "Run within hard safety limits", icon: Check },
  { id: "require_approval", label: "Review", detail: "One person must approve", icon: UserCheck },
  { id: "require_two_approvals", label: "Two approvals", detail: "Two distinct people approve", icon: Users },
  { id: "deny", label: "Deny", detail: "Block this action", icon: Ban },
  { id: "inherit", label: "Use limits", detail: "Apply amount and project rules", icon: SlidersHorizontal },
];

const MANAGED_PATCH_FIELDS = new Set<keyof PilotPolicyPayload>([
  "runtime_action_decision",
  "runtime_enabled",
  "runtime_max_tool_calls",
  "runtime_max_retries",
  "runtime_max_cost_usd",
  "runtime_approval_ttl_minutes",
  "runtime_amount_approval_threshold_usd",
  "runtime_amount_deny_threshold_usd",
]);

function emptyDraft(): PolicyRuleDraft {
  return {
    agentId: ANY,
    actionChoice: "email_send",
    customAction: "",
    environmentChoice: ANY,
    customEnvironment: "",
    outcome: "require_approval",
    description: "",
    maxToolCalls: "",
    maxRetries: "",
    maxCost: "",
    approvalTtl: "30",
    approvalThreshold: "",
    dualApprovalThreshold: "",
  };
}

function normalizedCustomValue(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9._:-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 64);
}

function resolvedAction(draft: PolicyRuleDraft): string {
  return draft.actionChoice === CUSTOM ? normalizedCustomValue(draft.customAction) : draft.actionChoice;
}

function resolvedEnvironment(draft: PolicyRuleDraft): string | null {
  if (draft.environmentChoice === CUSTOM) return normalizedCustomValue(draft.customEnvironment) || null;
  return draft.environmentChoice || null;
}

function optionalNonNegative(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function agentName(agents: AgentProfileResponse[], agentId: string): string {
  if (!agentId) return "All agents";
  const agent = agents.find((item) => item.id === agentId);
  return agent?.display_name || agent?.slug || "Selected agent";
}

function outcomeLabel(outcome: RuleOutcome): string {
  return OUTCOME_OPTIONS.find((item) => item.id === outcome)?.label ?? "Use limits";
}

export function buildPolicyRulePayload(
  draft: PolicyRuleDraft,
  agents: AgentProfileResponse[],
  existingPatch: Partial<PilotPolicyPayload> = {},
): RuntimePolicyRulePayload {
  const action = resolvedAction(draft);
  const environment = resolvedEnvironment(draft);
  const patch: Partial<PilotPolicyPayload> = {};

  for (const [key, value] of Object.entries(existingPatch) as Array<[keyof PilotPolicyPayload, PilotPolicyPayload[keyof PilotPolicyPayload]]>) {
    if (!MANAGED_PATCH_FIELDS.has(key)) {
      Object.assign(patch, { [key]: value });
    }
  }

  patch.runtime_enabled = true;
  patch.runtime_action_decision = draft.outcome;
  const maxToolCalls = optionalNonNegative(draft.maxToolCalls);
  const maxRetries = optionalNonNegative(draft.maxRetries);
  const maxCost = optionalNonNegative(draft.maxCost);
  const approvalTtl = optionalNonNegative(draft.approvalTtl);
  const approvalThreshold = optionalNonNegative(draft.approvalThreshold);
  const dualApprovalThreshold = optionalNonNegative(draft.dualApprovalThreshold);
  if (maxToolCalls != null) patch.runtime_max_tool_calls = Math.floor(maxToolCalls);
  if (maxRetries != null) patch.runtime_max_retries = Math.floor(maxRetries);
  if (maxCost != null) patch.runtime_max_cost_usd = maxCost;
  if (approvalTtl != null && approvalTtl > 0) patch.runtime_approval_ttl_minutes = Math.floor(approvalTtl);
  if (approvalThreshold != null) patch.runtime_amount_approval_threshold_usd = approvalThreshold;
  if (dualApprovalThreshold != null) patch.runtime_amount_deny_threshold_usd = dualApprovalThreshold;

  const scope = agentName(agents, draft.agentId);
  const actionName = actionLabel(action) || action.replaceAll("_", " ") || "Any action";
  return {
    name: `${scope}: ${actionName} - ${outcomeLabel(draft.outcome)}`.slice(0, 255),
    description: draft.description.trim() || null,
    agent_id: draft.agentId || null,
    action_type: action || null,
    environment,
    policy_patch: patch,
    priority: 0,
    is_enabled: true,
  };
}

function draftFromRule(rule: RuntimePolicyRuleResponse): PolicyRuleDraft {
  const knownAction = POLICY_ACTION_OPTIONS.some((item) => item.id === rule.action_type);
  const knownEnvironment = !rule.environment || ["production", "staging", "development"].includes(rule.environment);
  return {
    agentId: rule.agent_id ?? ANY,
    actionChoice: !rule.action_type ? ANY : knownAction ? rule.action_type : CUSTOM,
    customAction: knownAction ? "" : rule.action_type ?? "",
    environmentChoice: knownEnvironment ? rule.environment ?? ANY : CUSTOM,
    customEnvironment: knownEnvironment ? "" : rule.environment ?? "",
    outcome: rule.policy_patch.runtime_action_decision ?? "inherit",
    description: rule.description ?? "",
    maxToolCalls: rule.policy_patch.runtime_max_tool_calls?.toString() ?? "",
    maxRetries: rule.policy_patch.runtime_max_retries?.toString() ?? "",
    maxCost: rule.policy_patch.runtime_max_cost_usd?.toString() ?? "",
    approvalTtl: rule.policy_patch.runtime_approval_ttl_minutes?.toString() ?? "30",
    approvalThreshold: rule.policy_patch.runtime_amount_approval_threshold_usd?.toString() ?? "",
    dualApprovalThreshold: rule.policy_patch.runtime_amount_deny_threshold_usd?.toString() ?? "",
  };
}

export function PolicyRuleBuilder({
  agents,
  disabled,
  disabling,
  rules,
  saving,
  onDisable,
  onSave,
}: {
  agents: AgentProfileResponse[];
  disabled: boolean;
  disabling: boolean;
  rules: RuntimePolicyRuleResponse[];
  saving: boolean;
  onDisable: (ruleId: string) => void;
  onSave: (ruleId: string | null, payload: RuntimePolicyRulePayload) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PolicyRuleDraft>(() => emptyDraft());
  const [templateId, setTemplateId] = useState("custom");
  const [error, setError] = useState<string | null>(null);
  const editingRule = rules.find((rule) => rule.id === editingId) ?? null;
  const action = resolvedAction(draft);
  const environment = resolvedEnvironment(draft);
  const preview = useMemo(
    () => buildPolicyRulePayload(draft, agents, editingRule?.policy_patch),
    [agents, draft, editingRule?.policy_patch],
  );
  const scopeConflict = rules.find((rule) =>
    rule.is_enabled
    && rule.id !== editingId
    && (rule.agent_id ?? "") === draft.agentId
    && (rule.action_type ?? "") === action
    && (rule.environment ?? "") === (environment ?? ""),
  );

  useEffect(() => {
    if (editingId && !editingRule) {
      setEditingId(null);
      setDraft(emptyDraft());
    }
  }, [editingId, editingRule]);

  function update<Key extends keyof PolicyRuleDraft>(key: Key, value: PolicyRuleDraft[Key]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setError(null);
  }

  function applyTemplate(id: string) {
    const template = POLICY_RULE_TEMPLATES.find((item) => item.id === id) ?? POLICY_RULE_TEMPLATES[5];
    setTemplateId(template.id);
    setEditingId(null);
    setDraft({
      ...emptyDraft(),
      actionChoice: template.action,
      environmentChoice: template.environment,
      outcome: template.outcome,
      description: template.description,
    });
    setError(null);
  }

  function editRule(rule: RuntimePolicyRuleResponse) {
    setEditingId(rule.id);
    setTemplateId("custom");
    setDraft(draftFromRule(rule));
    setError(null);
  }

  function save() {
    if (draft.actionChoice === CUSTOM && !action) {
      setError("Enter the exact action name sent by the agent.");
      return;
    }
    if (draft.environmentChoice === CUSTOM && !environment) {
      setError("Enter an environment name or choose Any environment.");
      return;
    }
    if (draft.outcome === "inherit" && !draft.approvalThreshold && !draft.dualApprovalThreshold) {
      setError("Enter a money threshold or choose another outcome.");
      return;
    }
    onSave(editingId ?? scopeConflict?.id ?? null, preview);
  }

  return (
    <section className="panel policy-rule-builder" aria-labelledby="policy-rule-builder-title">
      <header className="policy-rule-builder-header">
        <div>
          <span className="dashboard-eyebrow">Agent-specific policies</span>
          <h2 id="policy-rule-builder-title">Create a clear WHEN / IN / THEN rule</h2>
          <p>Start from a job template or define the exact action your agent sends to Zroky.</p>
        </div>
        <label className="policy-template-select">
          <span>Start from template</span>
          <select aria-label="Start from template" value={templateId} onChange={(event) => applyTemplate(event.target.value)}>
            {POLICY_RULE_TEMPLATES.map((template) => (
              <option key={template.id} value={template.id}>{template.label}</option>
            ))}
          </select>
        </label>
      </header>

      <div className="policy-sentence-builder">
        <label>
          <span>When</span>
          <strong>Agent</strong>
          <select aria-label="Agent" value={draft.agentId} onChange={(event) => update("agentId", event.target.value)}>
            <option value="">All agents</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.display_name || agent.slug}</option>
            ))}
          </select>
        </label>

        <label>
          <span>Does</span>
          <strong>Action</strong>
          <select aria-label="Action" value={draft.actionChoice} onChange={(event) => update("actionChoice", event.target.value)}>
            <option value="">Any action</option>
            {POLICY_ACTION_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
            <option value={CUSTOM}>Custom action name</option>
          </select>
          {draft.actionChoice === CUSTOM ? (
            <input
              aria-label="Custom action name"
              maxLength={64}
              placeholder="e.g. publish_campaign"
              value={draft.customAction}
              onChange={(event) => update("customAction", event.target.value)}
            />
          ) : null}
        </label>

        <label>
          <span>In</span>
          <strong>Environment</strong>
          <select aria-label="Environment" value={draft.environmentChoice} onChange={(event) => update("environmentChoice", event.target.value)}>
            <option value="">Any environment</option>
            <option value="production">Production</option>
            <option value="staging">Staging</option>
            <option value="development">Development</option>
            <option value={CUSTOM}>Custom environment</option>
          </select>
          {draft.environmentChoice === CUSTOM ? (
            <input
              aria-label="Custom environment name"
              maxLength={64}
              placeholder="e.g. eu-production"
              value={draft.customEnvironment}
              onChange={(event) => update("customEnvironment", event.target.value)}
            />
          ) : null}
        </label>
      </div>

      <div className="policy-outcome-builder">
        <div>
          <span>Then</span>
          <strong>What should Zroky do?</strong>
        </div>
        <div className="policy-outcome-options" role="group" aria-label="Policy outcome">
          {OUTCOME_OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <button
                aria-pressed={draft.outcome === option.id}
                data-selected={draft.outcome === option.id}
                key={option.id}
                onClick={() => update("outcome", option.id)}
                type="button"
              >
                <Icon aria-hidden="true" size={17} />
                <span><strong>{option.label}</strong><small>{option.detail}</small></span>
              </button>
            );
          })}
        </div>
      </div>

      <details className="policy-rule-limits">
        <summary>Optional limits</summary>
        <div>
          <label><span>Max tool calls</span><input min="0" type="number" value={draft.maxToolCalls} onChange={(event) => update("maxToolCalls", event.target.value)} /></label>
          <label><span>Max retries</span><input min="0" type="number" value={draft.maxRetries} onChange={(event) => update("maxRetries", event.target.value)} /></label>
          <label><span>Max execution cost (USD)</span><input min="0" step="0.01" type="number" value={draft.maxCost} onChange={(event) => update("maxCost", event.target.value)} /></label>
          <label><span>Approval expires (minutes)</span><input min="1" type="number" value={draft.approvalTtl} onChange={(event) => update("approvalTtl", event.target.value)} /></label>
          <label><span>Money approval over (USD)</span><input min="0" step="0.01" type="number" value={draft.approvalThreshold} onChange={(event) => update("approvalThreshold", event.target.value)} /></label>
          <label><span>Two approvals over (USD)</span><input min="0" step="0.01" type="number" value={draft.dualApprovalThreshold} onChange={(event) => update("dualApprovalThreshold", event.target.value)} /></label>
        </div>
        <label className="policy-rule-description">
          <span>Internal note</span>
          <input placeholder="Why this rule exists" value={draft.description} onChange={(event) => update("description", event.target.value)} />
        </label>
      </details>

      <div className="policy-rule-result" aria-live="polite">
        <ShieldCheck aria-hidden="true" size={20} />
        <div>
          <strong>{agentName(agents, draft.agentId)} / {actionLabel(action) || action || "Any action"}</strong>
          <span>{environment ? `Only in ${environment}` : "In any environment"} / {outcomeLabel(draft.outcome)}</span>
        </div>
        <DashboardButton disabled={disabled} icon={<Save size={16} />} loading={saving} onClick={save} variant="primary">
          {editingId ? "Save policy rule" : scopeConflict ? "Replace existing policy" : "Create policy rule"}
        </DashboardButton>
        {editingId ? (
          <DashboardButton onClick={() => applyTemplate("custom")} variant="soft">Cancel edit</DashboardButton>
        ) : null}
        {!editingId && scopeConflict ? <small>This scope already has an active rule. Saving will replace it.</small> : null}
        {error ? <small role="alert">{error}</small> : null}
      </div>

      <div className="policy-rule-inventory">
        <header>
          <div><strong>Saved agent policies</strong><span>{rules.filter((rule) => rule.is_enabled).length} active</span></div>
          <DashboardButton icon={<Plus size={15} />} onClick={() => applyTemplate("custom")} size="sm" variant="soft">New rule</DashboardButton>
        </header>
        {rules.length ? (
          <div className="policy-rule-inventory-list">
            {rules.map((rule) => {
              const conditions = describePolicyPatch(rule.policy_patch);
              return (
                <article data-enabled={rule.is_enabled} key={rule.id}>
                  <div>
                    <strong>{rule.name}</strong>
                    <span>{conditions[0] || "Uses project policy outcome"}</span>
                  </div>
                  <span>{rule.is_enabled ? "Active" : "Disabled"}</span>
                  <DashboardButton aria-label={`Edit ${rule.name}`} icon={<Pencil size={15} />} onClick={() => editRule(rule)} size="sm" variant="soft" />
                  {rule.is_enabled ? (
                    <DashboardButton aria-label={`Disable ${rule.name}`} disabled={disabled} icon={<Trash2 size={15} />} loading={disabling} onClick={() => onDisable(rule.id)} size="sm" variant="danger" />
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : <p className="policy-rule-inventory-empty">No agent-specific policies yet. The project policy applies to every action.</p>}
      </div>
    </section>
  );
}
