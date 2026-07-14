import type {
  AgentProfileResponse,
  AgentRiskActionType,
  PilotPolicyPayload,
  RuntimePolicyMatchedRule,
  RuntimePolicyResolvePreviewResponse,
  RuntimePolicyRuleResponse,
} from "@/lib/api";
import type { StatusTone } from "@/lib/action-status";
import { formatUsd, humanize } from "@/lib/format";

export type PolicyActionOption = {
  id: AgentRiskActionType;
  label: string;
  operationKind: "TRANSFER" | "UPDATE" | "SEND" | "EXECUTE";
};

export const POLICY_ACTION_OPTIONS: PolicyActionOption[] = [
  { id: "refund", label: "Refund", operationKind: "TRANSFER" },
  { id: "payment_adjustment", label: "Payment adjustment", operationKind: "TRANSFER" },
  { id: "invoice_spend_approval", label: "Invoice spend approval", operationKind: "TRANSFER" },
  { id: "customer_record_update", label: "Customer record update", operationKind: "UPDATE" },
  { id: "ticket_close", label: "Ticket close", operationKind: "UPDATE" },
  { id: "database_record_update", label: "Database record update", operationKind: "UPDATE" },
  { id: "internal_api_mutation", label: "Internal API mutation", operationKind: "UPDATE" },
  { id: "email_send", label: "Email send", operationKind: "SEND" },
  { id: "deploy_change", label: "Deploy change", operationKind: "EXECUTE" },
  { id: "custom", label: "Custom action", operationKind: "EXECUTE" },
];

const ACTION_LABELS = new Map(POLICY_ACTION_OPTIONS.map((item) => [item.id, item.label]));

export type PolicyRuleCard = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  tone: StatusTone;
  scopeLabel: string;
  scopeParts: string[];
  conditionSummary: string;
  conditions: string[];
  priority: number;
  version: number;
  updatedAt: string;
  matched: boolean;
  matchIndex: number | null;
};

export type PolicyEffectiveView = {
  scopeLabel: string;
  matchedRules: RuntimePolicyMatchedRule[];
  summary: string;
  conditions: string[];
};

export type PolicyRulesView = {
  cards: PolicyRuleCard[];
  effective: PolicyEffectiveView | null;
};

function agentLabel(agents: AgentProfileResponse[], agentId: string | null | undefined): string | null {
  if (!agentId) return null;
  const agent = agents.find((item) => item.id === agentId);
  return agent?.display_name || agent?.slug || agentId;
}

export function actionLabel(actionType: string | null | undefined): string | null {
  if (!actionType) return null;
  return ACTION_LABELS.get(actionType as AgentRiskActionType) ?? humanize(actionType);
}

function boolLabel(value: boolean, enabledLabel: string, disabledLabel: string): string {
  return value ? enabledLabel : disabledLabel;
}

export function describePolicyPatch(patch: Partial<PilotPolicyPayload>): string[] {
  const conditions: string[] = [];
  if (patch.runtime_action_decision && patch.runtime_action_decision !== "inherit") {
    const outcomeLabels = {
      allow: "Allow within hard safety limits",
      require_approval: "Require one approval",
      require_two_approvals: "Require two approvals",
      deny: "Deny action",
    } as const;
    conditions.push(outcomeLabels[patch.runtime_action_decision]);
  }
  if (patch.kill_switch != null) {
    conditions.push(boolLabel(Boolean(patch.kill_switch), "Kill switch on", "Kill switch off"));
  }
  if (patch.runtime_enabled != null) {
    conditions.push(boolLabel(Boolean(patch.runtime_enabled), "Runtime gate enabled", "Runtime gate disabled"));
  }
  if (patch.runtime_amount_approval_threshold_usd != null) {
    conditions.push(`Approval above ${formatUsd(patch.runtime_amount_approval_threshold_usd)}`);
  }
  if (patch.runtime_amount_deny_threshold_usd != null) {
    conditions.push(`Deny above ${formatUsd(patch.runtime_amount_deny_threshold_usd)}`);
  }
  if (patch.runtime_max_cost_usd != null) {
    conditions.push(`Max cost ${formatUsd(patch.runtime_max_cost_usd)}`);
  }
  if (patch.runtime_approval_ttl_minutes != null) {
    conditions.push(`Approval TTL ${patch.runtime_approval_ttl_minutes}m`);
  }
  if (patch.runtime_sensitive_actions_require_approval != null) {
    conditions.push(
      boolLabel(
        Boolean(patch.runtime_sensitive_actions_require_approval),
        "Sensitive actions require approval",
        "Sensitive actions do not require approval",
      ),
    );
  }
  if (patch.runtime_changed_recipient_deny != null) {
    conditions.push(boolLabel(Boolean(patch.runtime_changed_recipient_deny), "Changed recipient denied", "Recipient changes allowed"));
  }
  if (patch.runtime_sequence_risk_enabled != null) {
    conditions.push(boolLabel(Boolean(patch.runtime_sequence_risk_enabled), "Sequence risk holds on", "Sequence risk holds off"));
  }
  if (patch.runtime_production_deploys_require_approval != null) {
    conditions.push(
      boolLabel(
        Boolean(patch.runtime_production_deploys_require_approval),
        "Production deploy approval",
        "Production deploys allowed",
      ),
    );
  }
  if (patch.runtime_block_pii_leak != null) {
    conditions.push(boolLabel(Boolean(patch.runtime_block_pii_leak), "PII leak blocked", "PII leak blocker off"));
  }
  if (patch.runtime_block_prompt_injected_external_action != null) {
    conditions.push(
      boolLabel(
        Boolean(patch.runtime_block_prompt_injected_external_action),
        "Prompt-injected external action blocked",
        "Prompt-injection blocker off",
      ),
    );
  }
  if (Array.isArray(patch.runtime_allowed_tools) && patch.runtime_allowed_tools.length > 0) {
    conditions.push(`Allowed tools: ${patch.runtime_allowed_tools.join(", ")}`);
  }
  if (Array.isArray(patch.runtime_sensitive_tools) && patch.runtime_sensitive_tools.length > 0) {
    conditions.push(`Sensitive tools: ${patch.runtime_sensitive_tools.join(", ")}`);
  }
  if (patch.runtime_max_tool_calls != null) {
    conditions.push(`${patch.runtime_max_tool_calls} max tool calls`);
  }
  if (patch.runtime_max_retries != null) {
    conditions.push(`${patch.runtime_max_retries} max retries`);
  }
  return conditions;
}

function scopeParts(rule: Pick<RuntimePolicyRuleResponse, "agent_id" | "action_type" | "environment">, agents: AgentProfileResponse[]): string[] {
  const parts: string[] = [];
  const agent = agentLabel(agents, rule.agent_id);
  if (agent) parts.push(agent);
  const action = actionLabel(rule.action_type);
  if (action) parts.push(action);
  if (rule.environment) parts.push(`env:${rule.environment}`);
  return parts;
}

function scopeLabelFromParts(parts: string[]): string {
  return parts.length > 0 ? parts.join(" / ") : "Project default";
}

function matchedRuleIndex(matched: RuntimePolicyMatchedRule[], ruleId: string): number | null {
  const index = matched.findIndex((item) => item.id === ruleId);
  return index >= 0 ? index + 1 : null;
}

export function buildPolicyRulesView({
  agents,
  preview,
  rules,
}: {
  agents: AgentProfileResponse[];
  preview?: RuntimePolicyResolvePreviewResponse | null;
  rules: RuntimePolicyRuleResponse[];
}): PolicyRulesView {
  const matched = preview?.matched_rules ?? [];
  const cards = [...rules]
    .sort((a, b) => Number(b.is_enabled) - Number(a.is_enabled) || b.priority - a.priority || b.updated_at.localeCompare(a.updated_at))
    .map((rule): PolicyRuleCard => {
      const parts = scopeParts(rule, agents);
      const conditions = describePolicyPatch(rule.policy_patch);
      const index = matchedRuleIndex(matched, rule.id);
      return {
        id: rule.id,
        name: rule.name,
        description: rule.description,
        enabled: rule.is_enabled,
        tone: !rule.is_enabled ? "neutral" : index ? "success" : "warning",
        scopeLabel: scopeLabelFromParts(parts),
        scopeParts: parts,
        conditionSummary: conditions.slice(0, 2).join(" · ") || "Runtime fields are scoped by this rule.",
        conditions,
        priority: rule.priority,
        version: rule.version,
        updatedAt: rule.updated_at,
        matched: index != null,
        matchIndex: index,
      };
    });

  const effectiveConditions = preview ? describePolicyPatch(preview.policy) : [];
  const effective: PolicyEffectiveView | null = preview
    ? {
        scopeLabel: "Selected scope",
        matchedRules: preview.matched_rules,
        summary:
          preview.matched_rules.length > 0
            ? `${preview.matched_rules.length} scoped rule${preview.matched_rules.length === 1 ? "" : "s"} matched.`
            : "Project default policy applies.",
        conditions: effectiveConditions,
      }
    : null;

  return { cards, effective };
}
