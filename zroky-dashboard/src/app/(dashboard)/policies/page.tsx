"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  LockKeyhole,
  PlayCircle,
  Plus,
  RefreshCw,
  Save,
  ShieldAlert,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  DashboardWorkspace,
  type DashboardMetric,
} from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import {
  getPilotPolicy,
  createRuntimePolicyRule,
  disableRuntimePolicyRule,
  dryRunRuntimePolicy,
  listAgentProfiles,
  listRuntimePolicyApprovals,
  listRuntimePolicyRules,
  resolveRuntimePolicyPreview,
  setRuntimePolicyKillSwitch,
  updateRuntimePolicyRule,
  updatePilotPolicy,
  type AgentProfileResponse,
  type AgentRiskActionType,
  type PilotPolicyPayload,
  type RuntimePolicyDryRunResponse,
  type RuntimePolicyDecisionResponse,
  type RuntimePolicyRulePayload,
  type RuntimePolicyRuleResponse,
} from "@/lib/api";
import type { StatusTone } from "@/lib/action-status";
import { formatDateTime } from "@/lib/format";
import {
  POLICY_ACTION_OPTIONS,
  buildPolicyRulesView,
  describePolicyPatch,
} from "@/lib/policy-rules-view";

const DASH = "-";
const ACTIVE_GUARDRAIL_COUNT = 5;
const ENVIRONMENT_OPTIONS = ["production", "staging", "development"];

type PolicyRuleForm = {
  name: string;
  description: string;
  agentId: string;
  actionType: AgentRiskActionType | "";
  environment: string;
  priority: string;
  isEnabled: boolean;
  runtimeEnabled: "inherit" | "enabled" | "disabled";
  sensitiveApproval: "inherit" | "enabled" | "disabled";
  approvalThreshold: string;
  denyThreshold: string;
  maxCost: string;
  approvalTtl: string;
  allowedTools: string;
  sensitiveTools: string;
};

function blankRuleForm(): PolicyRuleForm {
  return {
    name: "",
    description: "",
    agentId: "",
    actionType: "",
    environment: "",
    priority: "0",
    isEnabled: true,
    runtimeEnabled: "inherit",
    sensitiveApproval: "inherit",
    approvalThreshold: "",
    denyThreshold: "",
    maxCost: "",
    approvalTtl: "",
    allowedTools: "",
    sensitiveTools: "",
  };
}

function listToText(values: string[]): string {
  return values.join(", ");
}

function textToList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function triStateBoolean(value: "inherit" | "enabled" | "disabled"): boolean | undefined {
  if (value === "inherit") return undefined;
  return value === "enabled";
}

function ruleFormFromRule(rule: RuntimePolicyRuleResponse | null): PolicyRuleForm {
  if (!rule) return blankRuleForm();
  return {
    name: rule.name,
    description: rule.description ?? "",
    agentId: rule.agent_id ?? "",
    actionType: (rule.action_type as AgentRiskActionType | null) ?? "",
    environment: rule.environment ?? "",
    priority: String(rule.priority ?? 0),
    isEnabled: rule.is_enabled,
    runtimeEnabled:
      rule.policy_patch.runtime_enabled == null
        ? "inherit"
        : rule.policy_patch.runtime_enabled
          ? "enabled"
          : "disabled",
    sensitiveApproval:
      rule.policy_patch.runtime_sensitive_actions_require_approval == null
        ? "inherit"
        : rule.policy_patch.runtime_sensitive_actions_require_approval
          ? "enabled"
          : "disabled",
    approvalThreshold: rule.policy_patch.runtime_amount_approval_threshold_usd?.toString() ?? "",
    denyThreshold: rule.policy_patch.runtime_amount_deny_threshold_usd?.toString() ?? "",
    maxCost: rule.policy_patch.runtime_max_cost_usd?.toString() ?? "",
    approvalTtl: rule.policy_patch.runtime_approval_ttl_minutes?.toString() ?? "",
    allowedTools: listToText(rule.policy_patch.runtime_allowed_tools ?? []),
    sensitiveTools: listToText(rule.policy_patch.runtime_sensitive_tools ?? []),
  };
}

function patchFromRuleForm(form: PolicyRuleForm): Partial<PilotPolicyPayload> {
  const patch: Partial<PilotPolicyPayload> = {};
  const runtimeEnabled = triStateBoolean(form.runtimeEnabled);
  const sensitiveApproval = triStateBoolean(form.sensitiveApproval);
  const approvalThreshold = optionalNumber(form.approvalThreshold);
  const denyThreshold = optionalNumber(form.denyThreshold);
  const maxCost = optionalNumber(form.maxCost);
  const approvalTtl = optionalNumber(form.approvalTtl);
  const allowedTools = textToList(form.allowedTools);
  const sensitiveTools = textToList(form.sensitiveTools);

  if (runtimeEnabled != null) patch.runtime_enabled = runtimeEnabled;
  if (sensitiveApproval != null) patch.runtime_sensitive_actions_require_approval = sensitiveApproval;
  if (approvalThreshold != null) patch.runtime_amount_approval_threshold_usd = approvalThreshold;
  if (denyThreshold != null) patch.runtime_amount_deny_threshold_usd = denyThreshold;
  if (maxCost != null) patch.runtime_max_cost_usd = maxCost;
  if (approvalTtl != null) patch.runtime_approval_ttl_minutes = approvalTtl;
  if (allowedTools.length > 0) patch.runtime_allowed_tools = allowedTools;
  if (sensitiveTools.length > 0) patch.runtime_sensitive_tools = sensitiveTools;

  return patch;
}

function rulePayloadFromForm(form: PolicyRuleForm): RuntimePolicyRulePayload {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    agent_id: form.agentId || null,
    action_type: form.actionType || null,
    environment: form.environment || null,
    priority: Number(form.priority || 0),
    is_enabled: form.isEnabled,
    policy_patch: patchFromRuleForm(form),
  };
}

function agentOptionLabel(agent: AgentProfileResponse): string {
  return agent.display_name || agent.slug || agent.id;
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

function decisionTone(item: RuntimePolicyDecisionResponse): StatusTone {
  if (item.status === "allowed" || item.status === "approved") return "success";
  if (item.status === "blocked" || item.status === "rejected") return "danger";
  return "warning";
}

function decisionTitle(item: RuntimePolicyDecisionResponse): string {
  return item.action_type || item.tool_name || item.role || "Runtime action";
}

function decisionSubtitle(item: RuntimePolicyDecisionResponse): string {
  return (
    [item.agent_name, item.tool_name, item.call_id || item.trace_id]
      .filter(Boolean)
      .join(" / ") || "Runtime policy decision"
  );
}

function decisionReason(item: RuntimePolicyDecisionResponse): string {
  return item.reasons[0] || (item.requires_approval ? "Human approval required." : "Policy decision captured.");
}

function policyReadiness(policy: PilotPolicyPayload | null): {
  label: string;
  helper: string;
  tone: StatusTone;
} {
  if (!policy) {
    return {
      label: "Unknown",
      helper: "Policy could not be loaded yet.",
      tone: "warning",
    };
  }
  if (policy.kill_switch) {
    return {
      label: "Stopped",
      helper: "Kill switch is enabled. Autonomous actions should not proceed.",
      tone: "danger",
    };
  }
  if (!policy.runtime_enabled) {
    return {
      label: "Ungated",
      helper: "Runtime policy checks are disabled for this project.",
      tone: "warning",
    };
  }
  if (!policy.runtime_sensitive_actions_require_approval) {
    return {
      label: "Weak",
      helper: "Sensitive actions do not require approval.",
      tone: "warning",
    };
  }
  return {
    label: "Controlled",
    helper: "Runtime gate is active and sensitive actions require approval.",
    tone: "success",
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
  tone: StatusTone;
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
      copy: "The kill switch is on. Autonomous actions remain frozen until an operator reopens the project.",
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
      copy: "The runtime gate blocked risky actions and kept a decision trail for audit and evidence review.",
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

function NumberField({
  label,
  min,
  onChange,
  step,
  value,
}: {
  label: string;
  min?: number;
  onChange: (value: string) => void;
  step?: string;
  value: number | string;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        min={min}
        step={step}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function TextareaField({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
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
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [ruleForm, setRuleForm] = useState<PolicyRuleForm>(() => blankRuleForm());
  const [previewAgentId, setPreviewAgentId] = useState("");
  const [previewActionType, setPreviewActionType] = useState<AgentRiskActionType | "">("refund");
  const [previewEnvironment, setPreviewEnvironment] = useState("production");
  const [dryRunAmount, setDryRunAmount] = useState("600");
  const [dryRunResult, setDryRunResult] = useState<RuntimePolicyDryRunResponse | null>(null);
  const [killSwitchTarget, setKillSwitchTarget] = useState<boolean | null>(null);

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

  const agentsQuery = useQuery({
    queryKey: ["agents", "profiles", "policy-rules"],
    queryFn: ({ signal }) => listAgentProfiles({ limit: 200 }, signal),
    staleTime: 30_000,
    retry: false,
  });

  const rulesQuery = useQuery({
    queryKey: ["runtime-policy", "rules"],
    queryFn: ({ signal }) => listRuntimePolicyRules(null, signal),
    staleTime: 15_000,
    retry: false,
  });

  const previewQuery = useQuery({
    queryKey: ["runtime-policy", "resolve-preview", previewAgentId, previewActionType, previewEnvironment],
    queryFn: ({ signal }) =>
      resolveRuntimePolicyPreview(
        {
          agent_id: previewAgentId || null,
          action_type: previewActionType || null,
          environment: previewEnvironment || null,
        },
        signal,
      ),
    staleTime: 10_000,
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
    onSuccess: (response, enabled) => {
      setPolicy((current) => (current ? { ...current, kill_switch: response.enabled } : current));
      setKillSwitchTarget(null);
      setMessage(enabled ? "Kill switch enabled." : "Autonomy resumed.");
      void queryClient.invalidateQueries({ queryKey: ["pilot-policy"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Kill switch update failed.");
    },
  });

  const saveRuleMutation = useMutation({
    mutationFn: (payload: RuntimePolicyRulePayload) =>
      selectedRuleId
        ? updateRuntimePolicyRule(selectedRuleId, payload)
        : createRuntimePolicyRule(payload),
    onSuccess: (rule) => {
      setSelectedRuleId(rule.id);
      setRuleForm(ruleFormFromRule(rule));
      setMessage(selectedRuleId ? "Scoped rule updated." : "Scoped rule created.");
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "rules"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "resolve-preview"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["pilot-policy"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Scoped rule save failed.");
    },
  });

  const disableRuleMutation = useMutation({
    mutationFn: disableRuntimePolicyRule,
    onSuccess: (rule) => {
      setRuleForm(ruleFormFromRule(rule));
      setMessage("Scoped rule disabled.");
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "rules"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "resolve-preview"] });
      void queryClient.invalidateQueries({ queryKey: ["runtime-policy", "approvals"] });
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Scoped rule disable failed.");
    },
  });

  const dryRunMutation = useMutation({
    mutationFn: dryRunRuntimePolicy,
    onSuccess: (result) => {
      setDryRunResult(result);
      setMessage("Policy dry-run completed. Nothing was recorded.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Policy dry-run failed.");
    },
  });

  useEffect(() => {
    if (!policyQuery.data?.policy) return;
    setPolicy(policyQuery.data.policy);
    setAllowedTools(listToText(policyQuery.data.policy.runtime_allowed_tools));
    setSensitiveTools(listToText(policyQuery.data.policy.runtime_sensitive_tools));
  }, [policyQuery.data]);

  useEffect(() => {
    if (!selectedRuleId) {
      setRuleForm(blankRuleForm());
      return;
    }
    const selected = rulesQuery.data?.items.find((item) => item.id === selectedRuleId) ?? null;
    if (selected) {
      setRuleForm(ruleFormFromRule(selected));
    }
  }, [rulesQuery.data, selectedRuleId]);

  const readiness = useMemo(() => policyReadiness(policy), [policy]);
  const approvals = approvalsQuery.data?.items ?? [];
  const agents = useMemo(() => agentsQuery.data?.items ?? [], [agentsQuery.data?.items]);
  const rules = useMemo(() => rulesQuery.data?.items ?? [], [rulesQuery.data?.items]);
  const pendingApprovals = approvals.filter((item) => item.status === "pending_approval").length;
  const blockedActions = approvals.filter((item) => item.status === "blocked" || item.status === "rejected").length;
  const activeGuardrails = policy
    ? [
        policy.runtime_sensitive_actions_require_approval,
        policy.runtime_block_pii_leak,
        policy.runtime_block_prompt_injected_external_action,
        policy.runtime_production_deploys_require_approval,
        policy.runtime_changed_recipient_deny,
      ].filter(Boolean).length
    : 0;
  const latestDecisions = approvals.slice(0, 5);
  const rulesView = useMemo(
    () => buildPolicyRulesView({ agents, preview: previewQuery.data, rules }),
    [agents, previewQuery.data, rules],
  );
  const selectedAgent = agents.find((agent) => agent.id === previewAgentId) ?? null;
  const selectedRule = rules.find((rule) => rule.id === selectedRuleId) ?? null;
  const rulePatch = useMemo(() => patchFromRuleForm(ruleForm), [ruleForm]);
  const ruleConditions = useMemo(() => describePolicyPatch(rulePatch), [rulePatch]);
  const heroVerdict = policyVerdict({
    activeGuardrails,
    blockedActions,
    pendingApprovals,
    policy,
  });

  const metrics: DashboardMetric[] = [
    {
      id: "readiness",
      label: "Runtime action control",
      value: readiness.label,
      helper: readiness.helper,
      tone: readiness.tone,
      icon: <CheckCircle2 size={16} />,
    },
    {
      id: "gate",
      label: "Policy gate",
      value: policy?.runtime_enabled ? "Enabled" : "Disabled",
      helper: "Applies limits before risky autonomous actions continue.",
      tone: policy?.runtime_enabled ? "success" : "warning",
      icon: <SlidersHorizontal size={16} />,
    },
    {
      id: "pending",
      label: "Pending approvals",
      value: approvalsQuery.isLoading ? DASH : String(pendingApprovals),
      helper: "Approval queue items waiting on a human decision.",
      tone: pendingApprovals > 0 ? "warning" : "neutral",
      href: "/approvals",
      icon: <Clock3 size={16} />,
    },
    {
      id: "blocked",
      label: "Blocked actions",
      value: approvalsQuery.isLoading ? DASH : String(blockedActions),
      helper: "Rejected or blocked policy decisions visible in the audit trail.",
      tone: blockedActions > 0 ? "danger" : "neutral",
      href: "/approvals",
      icon: <AlertTriangle size={16} />,
    },
  ];

  function updatePolicyField<Key extends keyof PilotPolicyPayload>(key: Key, value: PilotPolicyPayload[Key]) {
    setPolicy((current) => (current ? { ...current, [key]: value } : current));
  }

  function updateRuleForm<Key extends keyof PolicyRuleForm>(key: Key, value: PolicyRuleForm[Key]) {
    setRuleForm((current) => ({ ...current, [key]: value }));
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

  function saveRule() {
    const payload = rulePayloadFromForm(ruleForm);
    if (!payload.name) {
      setMessage("Rule name is required.");
      return;
    }
    if (Object.keys(payload.policy_patch).length === 0) {
      setMessage("Add at least one condition before saving a scoped rule.");
      return;
    }
    setMessage(null);
    saveRuleMutation.mutate(payload);
  }

  function runDryRun() {
    const amount = optionalNumber(dryRunAmount) ?? 0;
    setDryRunResult(null);
    setMessage(null);
    dryRunMutation.mutate({
      agent_id: previewAgentId || null,
      agent_name: selectedAgent ? agentOptionLabel(selectedAgent) : null,
      action_type: previewActionType || null,
      tool_name: previewActionType || null,
      environment: previewEnvironment || null,
      external_action: true,
      impact_usd: amount,
      estimated_cost_usd: amount,
      tool_args: { amount, currency: "USD" },
      business_impact_summary: "Policy dry-run preview",
    });
  }

  function requestKillSwitchChange(enabled: boolean) {
    setMessage(null);
    if (killSwitchTarget === enabled) {
      killSwitchMutation.mutate(enabled);
      return;
    }
    setKillSwitchTarget(enabled);
  }

  const killSwitchActive = policy?.kill_switch === true;
  const killSwitchConfirmationActive = killSwitchTarget !== null;
  const killSwitchActionLabel =
    killSwitchTarget === true
      ? "Confirm kill switch"
      : killSwitchTarget === false
        ? "Confirm resume"
        : killSwitchActive
          ? "Resume autonomy"
          : "Arm kill switch";
  const killSwitchActionIcon =
    killSwitchTarget === false || (killSwitchTarget === null && killSwitchActive)
      ? <PlayCircle size={16} />
      : <ShieldAlert size={16} />;
  const killSwitchActionVariant =
    killSwitchTarget === false || (killSwitchTarget === null && killSwitchActive)
      ? "primary"
      : killSwitchTarget === true
        ? "danger"
        : "soft";

  const heroActions = (
    <>
      <DashboardButton
        icon={<RefreshCw size={16} />}
        onClick={() => {
          setMessage(null);
          void Promise.all([policyQuery.refetch(), approvalsQuery.refetch()]);
        }}
        disabled={policyQuery.isFetching || approvalsQuery.isFetching}
        variant="soft"
      >
        Refresh
      </DashboardButton>
      {killSwitchConfirmationActive && (
        <DashboardButton
          onClick={() => setKillSwitchTarget(null)}
          disabled={killSwitchMutation.isPending}
          variant="soft"
        >
          Cancel
        </DashboardButton>
      )}
      <DashboardButton
        icon={killSwitchActionIcon}
        disabled={killSwitchMutation.isPending || !policy}
        loading={killSwitchMutation.isPending}
        onClick={() => requestKillSwitchChange(killSwitchActive ? false : true)}
        variant={killSwitchActionVariant}
      >
        {killSwitchActionLabel}
      </DashboardButton>
      <DashboardButton
        icon={<Save size={16} />}
        disabled={!policy}
        loading={savePolicyMutation.isPending}
        onClick={savePolicy}
        variant="primary"
      >
        Save policy
      </DashboardButton>
    </>
  );

  return (
    <div className="dashboard-page policies-page">
      <DashboardVerdictHero
        eyebrow="Runtime Action Control"
        title={heroVerdict.title}
        copy={heroVerdict.copy}
        tone={heroVerdict.tone}
        pill={heroVerdict.badge}
        updatedLabel={formatDateTime(policyQuery.data?.updated_at)}
        actions={heroActions}
        notices={message ? <span role="status">{message}</span> : null}
      />

      <DashboardMetricStrip
        ariaLabel="Policy safety summary"
        metrics={metrics}
        columns={4}
      />

      {policyQuery.isLoading ? <div className="empty">Loading runtime policy...</div> : null}
      {policyQuery.isError ? (
        <div className="empty error">
          {policyQuery.error instanceof Error ? policyQuery.error.message : "Policy could not load."}
        </div>
      ) : null}

      {policy ? (
        <DashboardWorkspace
          className="policies-workspace"
          left={
            <>
              <section className="panel settings-control-panel" aria-label="Scoped policy rules">
                <header className="panel-header">
                  <div>
                    <h2>Scoped policy rules</h2>
                    <p>Layer per-agent, action-type, and environment rules over the project baseline.</p>
                  </div>
                  <DashboardButton
                    icon={<Plus size={16} />}
                    onClick={() => {
                      setSelectedRuleId(null);
                      setRuleForm(blankRuleForm());
                    }}
                    size="sm"
                    variant="soft"
                  >
                    New rule
                  </DashboardButton>
                </header>
                {rulesQuery.isLoading ? <div className="policy-empty-state">Loading scoped rules...</div> : null}
                {rulesQuery.isError ? (
                  <div className="policy-empty-state">
                    {rulesQuery.error instanceof Error ? rulesQuery.error.message : "Scoped rules could not load."}
                  </div>
                ) : null}
                {rulesView.cards.length > 0 ? (
                  <div className="policy-rule-list">
                    {rulesView.cards.map((rule) => (
                      <button
                        key={rule.id}
                        className="policy-rule-card"
                        data-selected={rule.id === selectedRuleId}
                        data-tone={rule.tone}
                        onClick={() => setSelectedRuleId(rule.id)}
                        type="button"
                      >
                        <span className="policy-rule-card-kicker">
                          {rule.enabled ? "Rule" : "Disabled"} · priority {rule.priority}
                          {rule.matchIndex ? ` · match #${rule.matchIndex}` : ""}
                        </span>
                        <strong>{rule.name}</strong>
                        <span>{rule.scopeLabel}</span>
                        <p>{rule.conditionSummary}</p>
                      </button>
                    ))}
                  </div>
                ) : !rulesQuery.isLoading ? (
                  <div className="policy-empty-state">
                    No scoped rules yet. Project default policy applies to every agent.
                  </div>
                ) : null}
              </section>

              <section className="panel settings-control-panel" aria-label="Scoped rule editor">
                <header className="panel-header">
                  <div>
                    <h2>{selectedRule ? "Edit scoped rule" : "Create scoped rule"}</h2>
                    <p>Rules are partial patches. Empty fields inherit from the broader policy layer.</p>
                  </div>
                  <StatusPill
                    value={ruleForm.isEnabled ? "enabled" : "disabled"}
                    label={ruleForm.isEnabled ? "Enabled" : "Disabled"}
                    tone={ruleForm.isEnabled ? "success" : "neutral"}
                  />
                </header>
                <div className="settings-form-grid">
                  <label>
                    <span>Rule name</span>
                    <input
                      value={ruleForm.name}
                      onChange={(event) => updateRuleForm("name", event.target.value)}
                      placeholder="Refund agent approval threshold"
                    />
                  </label>
                  <label>
                    <span>Agent scope</span>
                    <select
                      value={ruleForm.agentId}
                      onChange={(event) => updateRuleForm("agentId", event.target.value)}
                    >
                      <option value="">All agents</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agentOptionLabel(agent)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Action type</span>
                    <select
                      value={ruleForm.actionType}
                      onChange={(event) => updateRuleForm("actionType", event.target.value as AgentRiskActionType | "")}
                    >
                      <option value="">All action types</option>
                      {POLICY_ACTION_OPTIONS.map((action) => (
                        <option key={action.id} value={action.id}>
                          {action.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Environment</span>
                    <select
                      value={ruleForm.environment}
                      onChange={(event) => updateRuleForm("environment", event.target.value)}
                    >
                      <option value="">All environments</option>
                      {ENVIRONMENT_OPTIONS.map((env) => (
                        <option key={env} value={env}>
                          {env}
                        </option>
                      ))}
                    </select>
                  </label>
                  <NumberField
                    label="Priority"
                    value={ruleForm.priority}
                    onChange={(value) => updateRuleForm("priority", value)}
                  />
                  <ToggleRow
                    label="Rule enabled"
                    description="Disabled rules stay visible but do not affect runtime decisions."
                    checked={ruleForm.isEnabled}
                    onChange={(checked) => updateRuleForm("isEnabled", checked)}
                  />
                </div>
                <div className="settings-form-grid">
                  <label>
                    <span>Runtime gate</span>
                    <select
                      value={ruleForm.runtimeEnabled}
                      onChange={(event) => updateRuleForm("runtimeEnabled", event.target.value as PolicyRuleForm["runtimeEnabled"])}
                    >
                      <option value="inherit">Inherit</option>
                      <option value="enabled">Enabled</option>
                      <option value="disabled">Disabled</option>
                    </select>
                  </label>
                  <label>
                    <span>Sensitive approval</span>
                    <select
                      value={ruleForm.sensitiveApproval}
                      onChange={(event) => updateRuleForm("sensitiveApproval", event.target.value as PolicyRuleForm["sensitiveApproval"])}
                    >
                      <option value="inherit">Inherit</option>
                      <option value="enabled">Required</option>
                      <option value="disabled">Not required</option>
                    </select>
                  </label>
                  <NumberField
                    label="Approval threshold (USD)"
                    min={0}
                    step="0.01"
                    value={ruleForm.approvalThreshold}
                    onChange={(value) => updateRuleForm("approvalThreshold", value)}
                  />
                  <NumberField
                    label="Deny threshold (USD)"
                    min={0}
                    step="0.01"
                    value={ruleForm.denyThreshold}
                    onChange={(value) => updateRuleForm("denyThreshold", value)}
                  />
                  <NumberField
                    label="Max cost (USD)"
                    min={0}
                    step="0.01"
                    value={ruleForm.maxCost}
                    onChange={(value) => updateRuleForm("maxCost", value)}
                  />
                  <NumberField
                    label="Approval TTL minutes"
                    min={1}
                    value={ruleForm.approvalTtl}
                    onChange={(value) => updateRuleForm("approvalTtl", value)}
                  />
                </div>
                <div className="settings-form-grid">
                  <TextareaField
                    label="Allowed tools override"
                    value={ruleForm.allowedTools}
                    onChange={(value) => updateRuleForm("allowedTools", value)}
                    placeholder="ledger.lookup, crm.update"
                  />
                  <TextareaField
                    label="Sensitive tools override"
                    value={ruleForm.sensitiveTools}
                    onChange={(value) => updateRuleForm("sensitiveTools", value)}
                    placeholder="ledger.refund, email.send"
                  />
                  <TextareaField
                    label="Description"
                    value={ruleForm.description}
                    onChange={(value) => updateRuleForm("description", value)}
                    placeholder="Why this scoped control exists."
                  />
                </div>
                <div className="policy-rule-preview">
                  <strong>Patch preview</strong>
                  {ruleConditions.length > 0 ? (
                    <ul>
                      {ruleConditions.map((condition) => (
                        <li key={condition}>{condition}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No conditions selected yet.</p>
                  )}
                </div>
                <div className="policy-rule-actions">
                  <DashboardButton
                    icon={<Save size={16} />}
                    loading={saveRuleMutation.isPending}
                    onClick={saveRule}
                    variant="primary"
                  >
                    {selectedRule ? "Save rule" : "Create rule"}
                  </DashboardButton>
                  {selectedRule ? (
                    <DashboardButton
                      icon={<Trash2 size={16} />}
                      loading={disableRuleMutation.isPending}
                      onClick={() => disableRuleMutation.mutate(selectedRule.id)}
                      variant="danger"
                    >
                      Disable rule
                    </DashboardButton>
                  ) : null}
                </div>
              </section>

              <section className="panel settings-control-panel" aria-label="Runtime action control mandate">
                <header className="panel-header">
                  <div>
                    <h2>Runtime Action Control</h2>
                    <p>
                      This is the live project mandate the runtime gate reads before an agent can execute risky work.
                    </p>
                  </div>
                  <StatusPill
                    value={policy.kill_switch ? "stopped" : policy.runtime_enabled ? "controlled" : "ungated"}
                    label={policy.kill_switch ? "Kill switch on" : policy.runtime_enabled ? "Controlled" : "Ungated"}
                    tone={policy.kill_switch ? "danger" : policy.runtime_enabled ? "success" : "warning"}
                  />
                </header>

                <section className="policy-boundary-grid" aria-label="Current mandate boundary">
                  <article className="policy-boundary-card">
                    <span>Allowed surface</span>
                    <strong>{toolsLabel(policy.runtime_allowed_tools, "Open non-sensitive tools")}</strong>
                    <p>
                      {policy.runtime_allowed_tools.length > 0
                        ? policy.runtime_allowed_tools.join(", ")
                        : "Any non-sensitive tool may run inside the runtime limits."}
                    </p>
                  </article>
                  <article className="policy-boundary-card">
                    <span>Approval mandate</span>
                    <strong>{toolsLabel(policy.runtime_sensitive_tools, "No sensitive tools listed")}</strong>
                    <p>
                      {policy.runtime_sensitive_actions_require_approval
                        ? `Sensitive actions hold for ${policy.runtime_approval_ttl_minutes} minutes.`
                        : "Sensitive actions do not currently force human approval."}
                    </p>
                  </article>
                  <article className="policy-boundary-card">
                    <span>Threshold rules</span>
                    <strong>{formatUsd(policy.runtime_amount_approval_threshold_usd)} approval</strong>
                    <p>{formatUsd(policy.runtime_amount_deny_threshold_usd)} requires dual approval.</p>
                  </article>
                  <article className="policy-boundary-card">
                    <span>Execution limits</span>
                    <strong>{formatUsd(policy.runtime_max_cost_usd)} per action</strong>
                    <p>{policy.runtime_max_tool_calls} tool calls, {policy.runtime_max_retries} retries.</p>
                  </article>
                </section>
              </section>

              <section className="panel settings-control-panel" aria-label="Runtime control editor">
                <header className="panel-header">
                  <div>
                    <h2>Edit runtime mandate</h2>
                    <p>These fields are enforced by the runtime policy gate, not just saved as setup metadata.</p>
                  </div>
                  <LockKeyhole aria-hidden="true" />
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
                    label="Sequence risk holds"
                    description="Hold cross-action patterns that are unsafe together — bulk read then external send, repeated money movement, or credential change then external transfer — even when each action is individually allowed."
                    checked={policy.runtime_sequence_risk_enabled}
                    onChange={(checked) => updatePolicyField("runtime_sequence_risk_enabled", checked)}
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

                <div className="settings-form-grid">
                  <NumberField
                    label="Max tool calls"
                    min={0}
                    value={policy.runtime_max_tool_calls}
                    onChange={(value) => updatePolicyField("runtime_max_tool_calls", Number(value))}
                  />
                  <NumberField
                    label="Max retries"
                    min={0}
                    value={policy.runtime_max_retries}
                    onChange={(value) => updatePolicyField("runtime_max_retries", Number(value))}
                  />
                  <NumberField
                    label="Max cost per action (USD)"
                    min={0}
                    step="0.01"
                    value={policy.runtime_max_cost_usd}
                    onChange={(value) => updatePolicyField("runtime_max_cost_usd", Number(value))}
                  />
                  <NumberField
                    label="Approval TTL minutes"
                    min={1}
                    value={policy.runtime_approval_ttl_minutes}
                    onChange={(value) => updatePolicyField("runtime_approval_ttl_minutes", Number(value))}
                  />
                  <NumberField
                    label="Approval threshold (USD)"
                    min={0}
                    step="0.01"
                    value={policy.runtime_amount_approval_threshold_usd ?? ""}
                    onChange={(value) =>
                      updatePolicyField(
                        "runtime_amount_approval_threshold_usd",
                        value === "" ? null : Number(value),
                      )
                    }
                  />
                  <NumberField
                    label="Dual approval threshold (USD)"
                    min={0}
                    step="0.01"
                    value={policy.runtime_amount_deny_threshold_usd ?? ""}
                    onChange={(value) =>
                      updatePolicyField(
                        "runtime_amount_deny_threshold_usd",
                        value === "" ? null : Number(value),
                      )
                    }
                  />
                </div>

                <div className="settings-form-grid">
                  <TextareaField
                    label="Allowed tools"
                    value={allowedTools}
                    onChange={setAllowedTools}
                    placeholder="Leave empty to allow any non-sensitive tool, or comma-separate tool names."
                  />
                  <TextareaField
                    label="Sensitive tools"
                    value={sensitiveTools}
                    onChange={setSensitiveTools}
                    placeholder="payment, refund, delete, email"
                  />
                </div>
              </section>
            </>
          }
          right={
            <>
              <section className="panel settings-control-panel" aria-label="Effective policy preview">
                <header className="panel-header">
                  <div>
                    <h2>Effective policy</h2>
                    <p>Resolve the actual policy for one agent, action type, and environment before it reaches the gate.</p>
                  </div>
                  <StatusPill
                    value={previewQuery.data?.matched_rules.length ? "scoped" : "project_default"}
                    label={previewQuery.data?.matched_rules.length ? "Scoped" : "Project default"}
                    tone={previewQuery.data?.matched_rules.length ? "success" : "neutral"}
                  />
                </header>
                <div className="settings-form-grid policy-preview-controls">
                  <label>
                    <span>Agent</span>
                    <select value={previewAgentId} onChange={(event) => setPreviewAgentId(event.target.value)}>
                      <option value="">All agents</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agentOptionLabel(agent)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Action type</span>
                    <select
                      value={previewActionType}
                      onChange={(event) => setPreviewActionType(event.target.value as AgentRiskActionType | "")}
                    >
                      <option value="">All action types</option>
                      {POLICY_ACTION_OPTIONS.map((action) => (
                        <option key={action.id} value={action.id}>
                          {action.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Environment</span>
                    <select value={previewEnvironment} onChange={(event) => setPreviewEnvironment(event.target.value)}>
                      <option value="">All environments</option>
                      {ENVIRONMENT_OPTIONS.map((env) => (
                        <option key={env} value={env}>
                          {env}
                        </option>
                      ))}
                    </select>
                  </label>
                  <DashboardButton
                    icon={<RefreshCw size={16} />}
                    loading={previewQuery.isFetching}
                    onClick={() => void previewQuery.refetch()}
                    variant="soft"
                  >
                    Resolve
                  </DashboardButton>
                </div>
                <div className="policy-effective-summary">
                  <strong>{rulesView.effective?.summary ?? "Resolving policy..."}</strong>
                  {previewQuery.isError ? (
                    <p>{previewQuery.error instanceof Error ? previewQuery.error.message : "Effective policy could not load."}</p>
                  ) : null}
                  {rulesView.effective?.matchedRules.length ? (
                    <ol>
                      {rulesView.effective.matchedRules.map((rule) => (
                        <li key={rule.id}>
                          {rule.name} <span>specificity {rule.specificity}</span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p>No scoped rules matched this selection.</p>
                  )}
                  {rulesView.effective?.conditions.length ? (
                    <div className="policy-effective-conditions">
                      {rulesView.effective.conditions.slice(0, 8).map((condition) => (
                        <span key={condition}>{condition}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="policy-dry-run">
                  <div>
                    <strong>Policy dry-run · not recorded</strong>
                    <p>Use the same non-persisting policy path to preview allow, hold, or deny.</p>
                  </div>
                  <label>
                    <span>Test amount USD</span>
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      value={dryRunAmount}
                      onChange={(event) => setDryRunAmount(event.target.value)}
                    />
                  </label>
                  <DashboardButton
                    icon={<PlayCircle size={16} />}
                    loading={dryRunMutation.isPending}
                    onClick={runDryRun}
                    variant="primary"
                  >
                    Run dry-run
                  </DashboardButton>
                  {dryRunResult ? (
                    <div className="policy-dry-run-result" data-status={dryRunResult.status}>
                      <StatusPill
                        value={dryRunResult.status}
                        kind="runtime_policy"
                        label={decisionStatusLabel(dryRunResult.status)}
                        tone={dryRunResult.status === "blocked" ? "danger" : dryRunResult.requires_approval ? "warning" : "success"}
                      />
                      <p>{dryRunResult.reasons.join(" ") || "Policy would allow this action."}</p>
                    </div>
                  ) : null}
                </div>
              </section>

              <section className="panel settings-control-panel" aria-label="Latest runtime decisions">
                <header className="panel-header">
                  <div>
                    <h2>Latest runtime decisions</h2>
                    <p>Allow, hold, and block events generated when SDK or Gateway called the runtime gate.</p>
                  </div>
                  <DashboardButtonLink href="/approvals" size="sm" variant="soft">
                    Open approvals
                  </DashboardButtonLink>
                </header>
                {latestDecisions.length > 0 ? (
                  <div className="policy-decision-list">
                    {latestDecisions.map((item) => (
                      <article key={item.id} className="policy-decision-row" data-tone={decisionTone(item)}>
                        <div>
                          <strong>{decisionTitle(item)}</strong>
                          <span>{decisionSubtitle(item)}</span>
                        </div>
                        <p>{decisionReason(item)}</p>
                        <StatusPill
                          value={item.status}
                          kind="runtime_policy"
                          label={decisionStatusLabel(item.status)}
                          tone={decisionTone(item)}
                        />
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="policy-empty-state">
                    Runtime decisions will appear after an agent calls the policy gate.
                  </div>
                )}
              </section>

              <section className="panel settings-control-panel" aria-label="Policy evidence path">
                <header className="panel-header">
                  <div>
                    <h2>Evidence path</h2>
                    <p>Policy hits should be visible before damage and exportable after review.</p>
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
                    <DashboardButtonLink href="/approvals" size="sm" variant="soft">
                      Open
                    </DashboardButtonLink>
                  </div>
                  <div className="list-row">
                    <div className="list-main">
                      <strong>Trace evidence</strong>
                      <span>Policy decisions are captured as trace evidence when agents call the runtime gate.</span>
                    </div>
                    <DashboardButtonLink href="/evidence" size="sm" variant="soft">
                      Evidence
                    </DashboardButtonLink>
                  </div>
                </div>
              </section>
            </>
          }
        />
      ) : null}
    </div>
  );
}
