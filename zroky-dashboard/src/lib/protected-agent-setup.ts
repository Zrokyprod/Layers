export type ProtectedAgentTemplate = {
  id: string;
  label: string;
  agentName: string;
  workflowId: string;
  toolName: string;
  sampleInput: string;
  sampleArgs: string;
  mandate: string;
  allowedActions: string[];
  holdConditions: string[];
  systemOfRecord: string;
  requiredEvidence: string[];
  connectorInputs: string[];
  proofStatus: "packaged_full_proof" | "custom_connector_required";
  liveSmokeScenario?: "refund" | "customer-record";
};

export const protectedAgentTemplates: ProtectedAgentTemplate[] = [
  {
    id: "refund",
    label: "Refund / payment",
    agentName: "refund-ops-agent",
    workflowId: "refund_guardrail",
    toolName: "issue_refund",
    sampleInput: "refund duplicate charge for order ord_123",
    sampleArgs: `{
        orderId: "ord_123",
        amountMinor: 25000,
        currency: "USD",
        reason: "duplicate_charge",
      }`,
    mandate: "Issue bounded refunds only when order, customer, amount, and reason are present.",
    allowedActions: ["lookup order", "hold refund for approval", "issue refund under mandate"],
    holdConditions: ["refund over approved amount", "missing order owner", "duplicate refund risk"],
    systemOfRecord: "payment ledger refund record",
    requiredEvidence: ["refund transaction id", "ledger status", "amount/currency match"],
    connectorInputs: [
      "ledger/refund API base URL",
      "read-scoped ledger bearer token",
      "safe refund id",
      "amount, currency, and status fields",
    ],
    proofStatus: "packaged_full_proof",
    liveSmokeScenario: "refund",
  },
  {
    id: "devops",
    label: "DevOps / release",
    agentName: "release-ops-agent",
    workflowId: "release_guardrail",
    toolName: "deploy_change",
    sampleInput: "deploy service api-gateway to production",
    sampleArgs: `{
        service: "api-gateway",
        environment: "production",
        changeId: "chg_742",
      }`,
    mandate: "Deploy approved changes only when the change ticket, checks, and rollback path exist.",
    allowedActions: ["read deployment status", "run approved release", "pause unsafe rollout"],
    holdConditions: ["production deploy without approval", "failing checks", "no rollback command"],
    systemOfRecord: "CI deployment and incident status",
    requiredEvidence: ["deployment id", "commit sha", "post-deploy health check"],
    connectorInputs: [
      "deployment or CI run API",
      "service, environment, and change id",
      "post-deploy health endpoint",
      "rollback or cancel action",
    ],
    proofStatus: "custom_connector_required",
  },
  {
    id: "crm",
    label: "CRM / data",
    agentName: "crm-record-agent",
    workflowId: "crm_mutation_guardrail",
    toolName: "update_customer_record",
    sampleInput: "update customer billing contact for acct_902",
    sampleArgs: `{
        accountId: "acct_902",
        field: "billing_contact",
        newValue: "ops@example.com",
      }`,
    mandate: "Modify customer records only with account id, source proof, and field-level scope.",
    allowedActions: ["read customer record", "update approved fields", "create audit note"],
    holdConditions: ["identity field change", "bulk update", "missing source proof"],
    systemOfRecord: "CRM account record",
    requiredEvidence: ["record id", "field diff", "CRM audit entry"],
    connectorInputs: [
      "CRM/customer API base URL",
      "read-scoped CRM bearer token",
      "safe customer or account id",
      "fields to compare after mutation",
    ],
    proofStatus: "packaged_full_proof",
    liveSmokeScenario: "customer-record",
  },
  {
    id: "outreach",
    label: "Lifecycle / outreach",
    agentName: "lifecycle-outreach-agent",
    workflowId: "outreach_guardrail",
    toolName: "send_customer_email",
    sampleInput: "send renewal notice to account acct_902",
    sampleArgs: `{
        accountId: "acct_902",
        templateId: "renewal_notice_v2",
        recipient: "ops@example.com",
      }`,
    mandate: "Send customer outreach only to eligible recipients with approved templates.",
    allowedActions: ["check consent", "send approved template", "record delivery result"],
    holdConditions: ["missing consent", "manual freeform body", "large recipient segment"],
    systemOfRecord: "email provider delivery event",
    requiredEvidence: ["message id", "recipient status", "bounce/complaint check"],
    connectorInputs: [
      "email provider event API",
      "message id or campaign id",
      "delivery, bounce, and complaint endpoints",
      "consent or suppression-list record",
    ],
    proofStatus: "custom_connector_required",
  },
  {
    id: "procurement",
    label: "Procurement / spend",
    agentName: "procurement-agent",
    workflowId: "procurement_guardrail",
    toolName: "create_purchase_order",
    sampleInput: "create PO for approved vendor security scan",
    sampleArgs: `{
        vendorId: "ven_118",
        amountMinor: 420000,
        currency: "USD",
        budgetCode: "security-tools",
      }`,
    mandate: "Create spend commitments only inside approved vendor, budget, and amount limits.",
    allowedActions: ["validate vendor", "create purchase order", "route for approval"],
    holdConditions: ["new vendor", "budget mismatch", "amount over mandate"],
    systemOfRecord: "ERP purchase order",
    requiredEvidence: ["purchase order id", "approval status", "budget allocation"],
    connectorInputs: [
      "ERP or purchase-order API",
      "vendor and budget record id",
      "approval status endpoint",
      "amount, currency, and budget fields",
    ],
    proofStatus: "custom_connector_required",
  },
];

export const pilotHandoffSteps = [
  "Create project key",
  "Copy mandate and SDK or webhook bridge",
  "Connect system of record",
  "Run connector preflight",
  "Run full proof command",
  "Export evidence pack",
];

export const pilotHandoffCriteria = [
  "captured_call_linked",
  "unsafe_action_stopped",
  "connector_configured",
  "connector_health_verified",
  "real_connector_ready",
  "saved_test_endpoint_used",
  "matched_outcome_shown",
  "evidence_hash_visible",
  "evidence_json_exported",
  "not_verified_when_missing",
  "evidence_pack_passed",
  "secrets_redacted",
];

export function humanizeIntent(value: string | null) {
  if (!value) return null;
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function buildMandateStarter(template: ProtectedAgentTemplate) {
  return `agent: ${template.agentName}
workflow: ${template.workflowId}
mandate: ${template.mandate}
allowed_actions:
${template.allowedActions.map((action) => `  - ${action}`).join("\n")}
hold_for_approval:
${template.holdConditions.map((condition) => `  - ${condition}`).join("\n")}
block:
  - missing required identifiers
  - no trusted system-of-record path
  - repeat fail or not_verified outcome
outcome_verification:
  system_of_record: ${template.systemOfRecord}
  required_evidence:
${template.requiredEvidence.map((evidence) => `    - ${evidence}`).join("\n")}
status_contract:
  pass: outcome matched system of record
  warn: action allowed but evidence incomplete
  fail: mandate breach or wrong outcome
  not_verified: trusted proof missing`;
}

type WebhookBridgeConnector = "ledger_refund" | "crm_record" | "generic_rest";

function webhookBridgeConnector(template: ProtectedAgentTemplate): WebhookBridgeConnector {
  if (template.liveSmokeScenario === "refund") return "ledger_refund";
  if (template.liveSmokeScenario === "customer-record") return "crm_record";
  return "generic_rest";
}

function webhookBridgeActionType(template: ProtectedAgentTemplate): string {
  if (template.id === "refund") return "refund";
  if (template.id === "crm") return "customer_record_update";
  if (template.id === "devops") return "deploy_change";
  if (template.id === "outreach") return "email_send";
  if (template.id === "procurement") return "invoice_spend_approval";
  return "custom";
}

function operationKindForTemplate(template: ProtectedAgentTemplate): "EXECUTE" | "SEND" | "TRANSFER" | "UPDATE" {
  if (template.id === "refund" || template.id === "procurement") return "TRANSFER";
  if (template.id === "outreach") return "SEND";
  if (template.id === "devops") return "EXECUTE";
  return "UPDATE";
}

function pythonString(value: string): string {
  return JSON.stringify(value);
}

function sampleResource(template: ProtectedAgentTemplate): Record<string, string> {
  if (template.id === "refund") {
    return { id: "ord_123", system: template.systemOfRecord, type: "refund" };
  }
  if (template.id === "crm") {
    return { id: "acct_902", system: template.systemOfRecord, type: "customer_record" };
  }
  if (template.id === "devops") {
    return { id: "chg_742", system: template.systemOfRecord, type: "deployment" };
  }
  if (template.id === "outreach") {
    return { id: "acct_902", system: template.systemOfRecord, type: "customer_message" };
  }
  return { id: "ven_118", system: template.systemOfRecord, type: "purchase_order" };
}

function sampleParameters(template: ProtectedAgentTemplate): Record<string, string | number> {
  if (template.id === "refund") {
    return { amount_minor: 25000, currency: "USD", reason: "duplicate_charge", requested_change: template.toolName };
  }
  if (template.id === "crm") {
    return { field: "billing_contact", new_value: "ops@example.com", requested_change: template.toolName };
  }
  if (template.id === "devops") {
    return { environment: "production", service: "api-gateway", requested_change: template.toolName };
  }
  if (template.id === "outreach") {
    return { template_id: "renewal_notice_v2", recipient: "ops@example.com", requested_change: template.toolName };
  }
  return { amount_minor: 420000, currency: "USD", budget_code: "security-tools", requested_change: template.toolName };
}

export type ProtectedAgentSnippetOptions = {
  agentId?: string;
  apiBaseUrl?: string;
};

export function buildProtectedAgentSnippet(
  template: ProtectedAgentTemplate,
  projectId: string,
  options: ProtectedAgentSnippetOptions = {},
) {
  const agentId = options.agentId ?? "agent_profile_id";
  const apiBaseUrl = options.apiBaseUrl ?? "https://api.zroky.com";
  const actionType = webhookBridgeActionType(template);
  const operationKind = operationKindForTemplate(template);
  const resource = JSON.stringify(sampleResource(template), null, 4);
  const parameters = JSON.stringify(sampleParameters(template), null, 4);

  return `import os
import zroky

zroky.init(
    api_key=os.environ["ZROKY_API_KEY"],
    project=${pythonString(projectId)},
    agent_id=${pythonString(agentId)},
    ingest_url=os.environ.get("ZROKY_API_URL", ${pythonString(apiBaseUrl)}),
)

result = zroky.protect(
    contract_version="zroky.agent_action.v1",
    action=${pythonString(actionType)},
    operation_kind=${pythonString(operationKind)},
    environment="production",
    purpose={"summary": ${pythonString(template.mandate)}},
    resource=${resource},
    params=${parameters},
    execution_request={
        "capability": ${pythonString(operationKind)},
        "execution_plan": {
            "tool": ${pythonString(template.toolName)},
            "summary": ${pythonString(template.sampleInput)},
        },
    },
    trace_context={
        "agent_name": ${pythonString(template.agentName)},
        "workflow_id": ${pythonString(template.workflowId)},
    },
    raise_on_approval=False,
    wait_for_receipt=True,
)

print(result["proof_status"], result["receipt_status"])`;
}

function webhookBridgeClaim(template: ProtectedAgentTemplate): Record<string, unknown> {
  if (template.liveSmokeScenario === "refund") {
    return {
      refund_id: "rf_123",
      status: "succeeded",
      amount_usd: 250,
      currency: "USD",
    };
  }
  if (template.liveSmokeScenario === "customer-record") {
    return {
      customer_id: "cus_902",
      account_id: "acct_902",
      status: "active",
      email: "ops@example.com",
    };
  }
  return {
    record_ref: `${template.workflowId}_record_001`,
    status: "approved",
    system_of_record: template.systemOfRecord,
  };
}

export function buildWebhookBridgePayload(template: ProtectedAgentTemplate) {
  const connector = webhookBridgeConnector(template);
  const claimed = webhookBridgeClaim(template);
  const payload: Record<string, unknown> = {
    connector,
    call_id: `${template.workflowId}_call_001`,
    trace_id: `${template.workflowId}_trace_001`,
    runtime_policy_decision_id: `${template.workflowId}_decision_001`,
    action_type: webhookBridgeActionType(template),
    claimed,
    metadata: {
      agent_name: template.agentName,
      workflow_id: template.workflowId,
      setup_source: "protected_agent_setup",
    },
  };

  if (connector === "ledger_refund") {
    payload.refund_id = String(claimed.refund_id);
  } else if (connector === "crm_record") {
    payload.customer_id = String(claimed.customer_id);
  } else {
    payload.record_ref = String(claimed.record_ref);
  }

  return JSON.stringify(payload, null, 2);
}

export function buildWebhookBridgeCurl(template: ProtectedAgentTemplate) {
  return `curl -X POST "https://api.zroky.com/v1/outcomes/reconciliation/saved" \\
  -H "content-type: application/json" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  --data '${buildWebhookBridgePayload(template)}'`;
}

export function webhookBridgeDetail(template: ProtectedAgentTemplate) {
  if (template.liveSmokeScenario === "refund") {
    return "Use after the refund tool returns success; Zroky verifies the saved ledger/refund connector before evidence is trusted.";
  }
  if (template.liveSmokeScenario === "customer-record") {
    return "Use after the CRM mutation returns success; Zroky verifies the saved customer-record connector before evidence is trusted.";
  }
  return `Use after the action returns success; connect Generic REST so Zroky can read ${template.systemOfRecord}.`;
}

export function proofReadinessLabel(template: ProtectedAgentTemplate) {
  return template.proofStatus === "packaged_full_proof"
    ? "Packaged full proof runner"
    : "Custom connector required";
}

export function proofReadinessDetail(template: ProtectedAgentTemplate) {
  if (template.liveSmokeScenario === "refund") {
    return "Refund and payment agents can use the packaged ledger/refund preflight and full proof runner.";
  }
  if (template.liveSmokeScenario === "customer-record") {
    return "CRM and data agents can use the packaged customer-record preflight and full proof runner.";
  }
  return `This template has mandate and SDK verified-action coverage. Add a connector that reads ${template.systemOfRecord} before calling the pilot verified.`;
}

export function buildLiveSmokeCommand(template: ProtectedAgentTemplate) {
  if (template.liveSmokeScenario === "refund") {
    return [
      "python scripts/run_design_partner_install_kit.py",
      "--scenario refund",
      "--api-base-url https://api.zroky.com",
      "--api-key <zroky_api_key>",
      "--ledger-base-url https://ledger.example.com/api",
      "--ledger-bearer-token <ledger_token>",
      "--refund-id <refund_id>",
      "--json",
      "--write-summary artifacts/design-partner-refund-live-summary.json",
      "--write-evidence artifacts/design-partner-refund-live-evidence.json",
    ].join(" ");
  }

  if (template.liveSmokeScenario === "customer-record") {
    return [
      "python scripts/run_design_partner_install_kit.py",
      "--scenario customer-record",
      "--api-base-url https://api.zroky.com",
      "--api-key <zroky_api_key>",
      "--crm-base-url https://crm.example.com/api",
      "--crm-bearer-token <crm_token>",
      "--customer-id <customer_id>",
      "--json",
      "--write-summary artifacts/design-partner-crm-live-summary.json",
      "--write-evidence artifacts/design-partner-crm-live-evidence.json",
    ].join(" ");
  }

  return null;
}
