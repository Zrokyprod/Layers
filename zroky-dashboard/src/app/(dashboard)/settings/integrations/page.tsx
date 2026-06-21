"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Copy,
  DatabaseZap,
  Download,
  FileJson,
  GitPullRequest,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  Save,
} from "lucide-react";

import {
  disconnectGithubRepoConnection,
  getCustomerRecordConnectorStatus,
  getGithubConnectionStatus,
  getLedgerRefundConnectorStatus,
  getRuntimePolicyEvidencePack,
  getSlackInstallStatus,
  listOutcomeReconciliations,
  saveCustomerRecordConnectorConfig,
  saveLedgerRefundConnectorConfig,
  testCustomerRecordConnector,
  testLedgerRefundConnector,
  type CustomerRecordConnectorStatusResponse,
  type LedgerRefundConnectorStatusResponse,
  type OutcomeReconciliationView,
  type RuntimePolicyEvidencePackResponse,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
} from "@/lib/types";

type IntegrationState = {
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  ledgerConfig: LedgerRefundConnectorStatusResponse | null;
  customerConfig: CustomerRecordConnectorStatusResponse | null;
  outcomeChecks: OutcomeReconciliationView[];
};

type ConnectorEvidenceKind = "ledger" | "customer";

type ConnectorEvidenceState = {
  kind: ConnectorEvidenceKind;
  checkId: string;
  pack: RuntimePolicyEvidencePackResponse;
};

type ConnectorGuidanceInput = {
  kind: ConnectorEvidenceKind;
  connected: boolean;
  health: string;
  verdict: string | null | undefined;
  errorCode: string | null | undefined;
  httpStatus: unknown;
  retryable: boolean | null | undefined;
};

type ConnectorPreflightSummaryInput = {
  kind: ConnectorEvidenceKind;
  connected: boolean;
  health: string;
  verdict: string | null | undefined;
  errorCode: string | null | undefined;
  error: string | null | undefined;
  httpStatus: unknown;
  attempts: unknown;
  retryable: boolean | null | undefined;
  guidance: string;
  readyForPilot: boolean;
  latestCheck: OutcomeReconciliationView | null;
  failedAttempts: OutcomeReconciliationView[];
};

type LedgerConnectorForm = {
  baseUrl: string;
  pathTemplate: string;
  recordPath: string;
  bearerToken: string;
  testRefundId: string;
  testAmountUsd: string;
  testCurrency: string;
  testStatus: string;
};

const defaultLedgerForm: LedgerConnectorForm = {
  baseUrl: "",
  pathTemplate: "/refunds/{refund_id}",
  recordPath: "data",
  bearerToken: "",
  testRefundId: "",
  testAmountUsd: "42.50",
  testCurrency: "USD",
  testStatus: "posted",
};

type CustomerConnectorForm = {
  baseUrl: string;
  pathTemplate: string;
  recordPath: string;
  bearerToken: string;
  testCustomerId: string;
  testEmail: string;
  testStatus: string;
  testAccountId: string;
};

const defaultCustomerForm: CustomerConnectorForm = {
  baseUrl: "",
  pathTemplate: "/customers/{customer_id}",
  recordPath: "data",
  bearerToken: "",
  testCustomerId: "",
  testEmail: "owner@example.com",
  testStatus: "active",
  testAccountId: "acct_1001",
};

function integrationStatus(connected: boolean) {
  return connected ? "Connected" : "Not connected";
}

function isProblemMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes("failed") || text.includes("could not") || text.includes("error");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function connectorMetadata(item: OutcomeReconciliationView | null): Record<string, unknown> {
  if (!item || !isRecord(item.metadata)) return {};
  const connector = item.metadata.connector;
  return isRecord(connector) ? connector : {};
}

function textValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function boolValue(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  if (["true", "1", "yes"].includes(normalized)) return true;
  if (["false", "0", "no"].includes(normalized)) return false;
  return null;
}

function isLedgerRefundCheck(item: OutcomeReconciliationView) {
  const metadata = isRecord(item.metadata) ? item.metadata : {};
  return item.connector_type === "ledger_refund_api" || metadata.connector_kind === "ledger_refund_api";
}

function isCustomerRecordCheck(item: OutcomeReconciliationView) {
  const metadata = isRecord(item.metadata) ? item.metadata : {};
  return item.connector_type === "customer_record_api" || metadata.connector_kind === "customer_record_api";
}

function connectorStatus(check: OutcomeReconciliationView | null) {
  if (!check) return "No proof yet";
  if (check.verdict === "matched") return "Verified";
  if (check.verdict === "mismatched") return "Mismatch";
  return "Not verified";
}

function connectorHealthLabel(value: string | null | undefined) {
  if (!value) return "Not verified";
  if (value === "not_configured") return "Not configured";
  if (value === "not_verified") return "Not verified";
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function connectorVerdictLabel(value: string | null | undefined) {
  if (!value) return "No run yet";
  return connectorHealthLabel(value);
}

function connectorErrorLabel(
  errorCode: string | null | undefined,
  error: string | null | undefined,
  retryable: boolean | null | undefined,
) {
  const code = textValue(errorCode);
  const rawError = textValue(error);
  if (!code && !rawError) return "None";
  const label = connectorHealthLabel(code ?? rawError);
  return retryable ? `${label} / retryable` : label;
}

function connectorFixGuidance({
  kind,
  connected,
  health,
  verdict,
  errorCode,
  httpStatus,
  retryable,
}: ConnectorGuidanceInput) {
  const surface = kind === "ledger" ? "ledger/refund" : "CRM/customer";
  const code = textValue(errorCode)?.toLowerCase();
  const status = textValue(httpStatus);

  if (!connected) {
    return "Save connector config, then run preflight before pilot handoff.";
  }
  if (verdict === "mismatched") {
    return `Fix ${surface} mismatch: compare claimed fields with the system-of-record record, then rerun preflight.`;
  }
  if (code === "auth_failed" || status === "401" || status === "403") {
    return `Fix ${surface} auth: rotate the bearer token, confirm scopes, then rerun preflight.`;
  }
  if (code === "connector_timeout") {
    return `Fix ${surface} reachability: confirm the API is public HTTPS, allowlisted, and responds within timeout.`;
  }
  if (code === "rate_limited" || status === "429") {
    return `Fix ${surface} throttling: raise the partner API limit or rerun after the retry window.`;
  }
  if (code === "connector_config_invalid") {
    return `Fix ${surface} config: use HTTPS, a relative path template, and the required record id placeholder.`;
  }
  if (code === "upstream_retryable_http_error" || retryable) {
    return `Fix ${surface} upstream: the partner API returned a retryable error; retry after recovery.`;
  }
  if (code === "upstream_http_error" || status === "404") {
    return `Fix ${surface} lookup: verify base URL, path template, record path, and the test record id.`;
  }
  if (health === "healthy" && verdict === "matched") {
    return "Preflight ready: connector matched ground truth and can support the buyer proof.";
  }
  return "Run preflight from this saved connector; do not pass handoff until health is Healthy and verdict is Matched.";
}

function connectorPillClass(check: OutcomeReconciliationView | null) {
  if (!check) return "pill";
  if (check.verdict === "matched") return "pill pill-green";
  if (check.verdict === "mismatched") return "pill pill-red";
  return "pill pill-yellow";
}

function connectorEvidenceLabel(kind: ConnectorEvidenceKind) {
  return kind === "ledger" ? "Ledger" : "Customer record";
}

function connectorPreflightLabel(kind: ConnectorEvidenceKind) {
  return kind === "ledger" ? "Ledger refund" : "Customer record";
}

function connectorPreflightKind(kind: ConnectorEvidenceKind) {
  return kind === "ledger" ? "ledger_refund_api" : "customer_record_api";
}

function evidenceStatusLabel(value: string) {
  if (value === "not_verified") return "Not verified";
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function evidenceMatchedOutcome(pack: RuntimePolicyEvidencePackResponse) {
  return pack.outcome_reconciliation.find((item) => item.verdict === "matched") ?? null;
}

function safeEvidenceFilePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]+/g, "_");
}

function downloadJsonFile(payload: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function downloadConnectorEvidencePack(pack: RuntimePolicyEvidencePackResponse, kind: ConnectorEvidenceKind) {
  downloadJsonFile(pack, `zroky-${kind}-evidence-${safeEvidenceFilePart(pack.decision_id)}.json`);
}

function maskHost(hostname: string) {
  const parts = hostname.split(".").filter(Boolean);
  if (parts.length <= 1) return "masked-host";
  return `${parts[0]}.***`;
}

function maskedConnectorUrl(value: unknown) {
  const raw = textValue(value);
  if (!raw) return "Waiting for first check";
  try {
    const url = new URL(raw);
    return `${url.protocol}//${maskHost(url.hostname)}/...`;
  } catch {
    return "Masked connector URL";
  }
}

function commandValue(value: string, fallback: string) {
  const trimmed = value.trim();
  return trimmed || fallback;
}

function ledgerPreflightCommand(form: LedgerConnectorForm) {
  return `python scripts/run_design_partner_install_kit.py --scenario refund --preflight-only --api-base-url https://api.zroky.ai --api-key <zroky_api_key> --ledger-base-url ${commandValue(form.baseUrl, "https://ledger.example.com/api")} --ledger-bearer-token <ledger_token> --refund-id ${commandValue(form.testRefundId, "<refund_id>")} --json --write-summary artifacts/design-partner-refund-preflight-summary.json`;
}

function customerPreflightCommand(form: CustomerConnectorForm) {
  return `python scripts/run_design_partner_install_kit.py --scenario customer-record --preflight-only --api-base-url https://api.zroky.ai --api-key <zroky_api_key> --crm-base-url ${commandValue(form.baseUrl, "https://crm.example.com/api")} --crm-bearer-token <crm_token> --customer-id ${commandValue(form.testCustomerId, "<customer_id>")} --json --write-summary artifacts/design-partner-crm-preflight-summary.json`;
}

function ledgerConnectorTemplate(form: LedgerConnectorForm) {
  const amount = Number(form.testAmountUsd.trim());
  const amountUsd = Number.isFinite(amount) ? amount : 42.18;
  const refundId = commandValue(form.testRefundId, "RF-1001");
  const currency = commandValue(form.testCurrency, "USD").toUpperCase();
  const status = commandValue(form.testStatus, "posted");
  return {
    connector_type: "ledger_refund_api",
    config_endpoint: "/v1/integrations/system-of-record/ledger-refund/config",
    status_endpoint: "/v1/integrations/system-of-record/ledger-refund/status",
    test_endpoint: "/v1/integrations/system-of-record/ledger-refund/test",
    config_payload: {
      base_url: commandValue(form.baseUrl, "https://ledger.example.com/api"),
      path_template: commandValue(form.pathTemplate, "/refunds/{refund_id}"),
      record_path: commandValue(form.recordPath, "data"),
      bearer_token: "<ledger_bearer_token>",
    },
    test_payload: {
      refund_id: refundId,
      claimed: {
        refund_id: refundId,
        amount_usd: amountUsd,
        currency,
        status,
      },
      match_fields: ["refund_id", "amount_usd", "currency", "status"],
      amount_usd: amountUsd,
      currency,
      metadata: {
        install_kit: "design_partner_refund_v1",
        partner_run_id: "<partner_run_id>",
      },
    },
    pass_criteria: {
      connector_health_status: "healthy",
      outcome_verdict: "matched",
      last_attempts: ">=1",
      last_error_code: null,
      last_retryable: null,
    },
  };
}

function customerConnectorTemplate(form: CustomerConnectorForm) {
  const customerId = commandValue(form.testCustomerId, "CUS-1001");
  return {
    connector_type: "customer_record_api",
    config_endpoint: "/v1/integrations/system-of-record/customer-record/config",
    status_endpoint: "/v1/integrations/system-of-record/customer-record/status",
    test_endpoint: "/v1/integrations/system-of-record/customer-record/test",
    config_payload: {
      base_url: commandValue(form.baseUrl, "https://crm.example.com/api"),
      path_template: commandValue(form.pathTemplate, "/customers/{customer_id}"),
      record_path: commandValue(form.recordPath, "data"),
      bearer_token: "<crm_bearer_token>",
    },
    test_payload: {
      customer_id: customerId,
      claimed: {
        customer_id: customerId,
        email: commandValue(form.testEmail, "owner@example.com"),
        account_id: commandValue(form.testAccountId, "acct_1001"),
        status: commandValue(form.testStatus, "active"),
      },
      match_fields: ["customer_id", "email", "account_id", "status"],
      metadata: {
        install_kit: "design_partner_crm_v1",
        partner_run_id: "<partner_run_id>",
      },
    },
    pass_criteria: {
      connector_health_status: "healthy",
      outcome_verdict: "matched",
      last_attempts: ">=1",
      last_error_code: null,
      last_retryable: null,
    },
  };
}

function connectorReadyForPilot(
  connected: boolean,
  health: string,
  verdict: string | null | undefined,
  errorCode: string | null | undefined,
) {
  return connected && health === "healthy" && verdict === "matched" && !textValue(errorCode);
}

function failedPreflightAttempts(checks: OutcomeReconciliationView[]) {
  return checks.filter((check) => check.verdict !== "matched").slice(0, 4);
}

function preflightCheckIssue(check: OutcomeReconciliationView) {
  const metadata = connectorMetadata(check);
  const issue = connectorErrorLabel(
    textValue(metadata.error_code),
    textValue(metadata.error),
    boolValue(metadata.retryable),
  );
  if (issue !== "None") return issue;
  if (check.verdict === "mismatched") return "Mismatched outcome";
  return check.reason ? connectorHealthLabel(check.reason) : connectorStatus(check);
}

function preflightCheckHttpStatus(check: OutcomeReconciliationView) {
  return textValue(connectorMetadata(check).http_status) ?? "No response";
}

function preflightCheckAttempts(check: OutcomeReconciliationView) {
  const attempts = textValue(connectorMetadata(check).attempts);
  if (!attempts) return "No retry data";
  return attempts === "1" ? "1 attempt" : `${attempts} attempts`;
}

function preflightCheckSummary(check: OutcomeReconciliationView | null) {
  if (!check) return null;
  const metadata = connectorMetadata(check);
  return {
    id: check.id,
    verdict: check.verdict,
    system_ref: check.system_ref,
    reason: check.reason,
    checked_at: check.checked_at,
    runtime_policy_decision_id: check.runtime_policy_decision_id,
    call_id: check.call_id,
    trace_id: check.trace_id,
    error_code: textValue(metadata.error_code),
    error_label: preflightCheckIssue(check),
    http_status: textValue(metadata.http_status),
    attempts: textValue(metadata.attempts),
    retryable: boolValue(metadata.retryable),
  };
}

function buildConnectorPreflightSummary({
  kind,
  connected,
  health,
  verdict,
  errorCode,
  error,
  httpStatus,
  attempts,
  retryable,
  guidance,
  readyForPilot,
  latestCheck,
  failedAttempts,
}: ConnectorPreflightSummaryInput) {
  return {
    schema_version: "zroky_connector_preflight_summary.v1",
    connector_kind: connectorPreflightKind(kind),
    generated_at: new Date().toISOString(),
    ready_for_pilot_handoff: readyForPilot,
    status: {
      connected,
      health_status: health,
      last_verdict: verdict ?? latestCheck?.verdict ?? "not_verified",
      last_error_code: textValue(errorCode),
      last_error_label: connectorErrorLabel(errorCode, error, retryable),
      last_http_status: textValue(httpStatus),
      last_attempts: textValue(attempts),
      last_retryable: retryable ?? null,
    },
    latest_check: preflightCheckSummary(latestCheck),
    failed_attempts: failedAttempts.map(preflightCheckSummary),
    fix_guidance: guidance,
  };
}

function ledgerRefundPayloadSnippet() {
  return `curl -X POST "$ZROKY_API_BASE/v1/integrations/system-of-record/ledger-refund/test" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "refund_id": "RF-1001",
    "claimed": {
      "refund_id": "RF-1001",
      "amount_usd": 42.18,
      "currency": "USD",
      "status": "posted"
    },
    "match_fields": ["refund_id", "amount_usd", "currency", "status"],
    "amount_usd": 42.18,
    "currency": "USD"
  }'`;
}

function customerRecordPayloadSnippet() {
  return `curl -X POST "$ZROKY_API_BASE/v1/integrations/system-of-record/customer-record/test" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "customer_id": "CUS-1001",
    "claimed": {
      "customer_id": "CUS-1001",
      "email": "owner@example.com",
      "status": "active",
      "account_id": "acct_1001"
    },
    "match_fields": ["customer_id", "email", "status", "account_id"]
  }'`;
}

function formFromLedgerConfig(
  config: LedgerRefundConnectorStatusResponse | null,
  previous: LedgerConnectorForm,
): LedgerConnectorForm {
  if (!config?.connected) return previous;
  return {
    ...previous,
    baseUrl: config.base_url ?? previous.baseUrl,
    pathTemplate: config.path_template ?? previous.pathTemplate,
    recordPath: config.record_path ?? previous.recordPath,
    bearerToken: "",
  };
}

function formFromCustomerConfig(
  config: CustomerRecordConnectorStatusResponse | null,
  previous: CustomerConnectorForm,
): CustomerConnectorForm {
  if (!config?.connected) return previous;
  return {
    ...previous,
    baseUrl: config.base_url ?? previous.baseUrl,
    pathTemplate: config.path_template ?? previous.pathTemplate,
    recordPath: config.record_path ?? previous.recordPath,
    bearerToken: "",
  };
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export default function IntegrationsSettingsPage() {
  const [state, setState] = useState<IntegrationState>({
    github: null,
    slack: null,
    ledgerConfig: null,
    customerConfig: null,
    outcomeChecks: [],
  });
  const [ledgerForm, setLedgerForm] = useState<LedgerConnectorForm>(defaultLedgerForm);
  const [customerForm, setCustomerForm] = useState<CustomerConnectorForm>(defaultCustomerForm);
  const [loading, setLoading] = useState(true);
  const [savingLedger, setSavingLedger] = useState(false);
  const [testingLedger, setTestingLedger] = useState(false);
  const [savingCustomer, setSavingCustomer] = useState(false);
  const [testingCustomer, setTestingCustomer] = useState(false);
  const [evidenceLoadingFor, setEvidenceLoadingFor] = useState<string | null>(null);
  const [connectorEvidence, setConnectorEvidence] = useState<ConnectorEvidenceState | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const [githubResult, slackResult, ledgerConfigResult, customerConfigResult, outcomeResult] = await Promise.allSettled([
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
      getLedgerRefundConnectorStatus(),
      getCustomerRecordConnectorStatus(),
      listOutcomeReconciliations({ limit: 25 }),
    ]);
    const ledgerConfig = ledgerConfigResult.status === "fulfilled" ? ledgerConfigResult.value : null;
    const customerConfig = customerConfigResult.status === "fulfilled" ? customerConfigResult.value : null;

    setState({
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      ledgerConfig,
      customerConfig,
      outcomeChecks: outcomeResult.status === "fulfilled" ? outcomeResult.value.items : [],
    });
    setLedgerForm((prev) => formFromLedgerConfig(ledgerConfig, prev));
    setCustomerForm((prev) => formFromCustomerConfig(customerConfig, prev));

    const failures = [githubResult, slackResult, ledgerConfigResult, customerConfigResult, outcomeResult].filter((result) => result.status === "rejected");
    if (failures.length > 0) {
      setMessage("Some integration status checks could not load. Verify backend connectivity and admin access.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const githubConnected = Boolean(state.github?.connected);
  const slackConnected = Boolean(state.slack?.connected);
  const ledgerConnected = Boolean(state.ledgerConfig?.connected);
  const customerConnected = Boolean(state.customerConfig?.connected);
  const ledgerRefundChecks = state.outcomeChecks.filter(isLedgerRefundCheck);
  const customerRecordChecks = state.outcomeChecks.filter(isCustomerRecordCheck);
  const latestLedgerRefundCheck = ledgerRefundChecks[0] ?? null;
  const latestCustomerRecordCheck = customerRecordChecks[0] ?? null;
  const ledgerMetadata = connectorMetadata(latestLedgerRefundCheck);
  const customerMetadata = connectorMetadata(latestCustomerRecordCheck);
  const ledgerVerified = latestLedgerRefundCheck?.verdict === "matched";
  const customerVerified = latestCustomerRecordCheck?.verdict === "matched";
  const readyCount = [githubConnected, slackConnected, ledgerConnected && ledgerVerified, customerConnected && customerVerified].filter(Boolean).length;
  const ledgerHealth = state.ledgerConfig?.health_status ?? (ledgerConnected ? "not_verified" : "not_configured");
  const customerHealth = state.customerConfig?.health_status ?? (customerConnected ? "not_verified" : "not_configured");
  const ledgerLastVerdict = state.ledgerConfig?.last_verdict ?? latestLedgerRefundCheck?.verdict;
  const customerLastVerdict = state.customerConfig?.last_verdict ?? latestCustomerRecordCheck?.verdict;
  const ledgerLastRetryable = state.ledgerConfig?.last_retryable ?? boolValue(ledgerMetadata.retryable);
  const customerLastRetryable = state.customerConfig?.last_retryable ?? boolValue(customerMetadata.retryable);
  const ledgerErrorCode = state.ledgerConfig?.last_error_code ?? textValue(ledgerMetadata.error_code);
  const customerErrorCode = state.customerConfig?.last_error_code ?? textValue(customerMetadata.error_code);
  const ledgerRawError = state.ledgerConfig?.last_error ?? textValue(ledgerMetadata.error);
  const customerRawError = state.customerConfig?.last_error ?? textValue(customerMetadata.error);
  const ledgerHttpStatusValue = state.ledgerConfig?.last_http_status ?? ledgerMetadata.http_status;
  const customerHttpStatusValue = state.customerConfig?.last_http_status ?? customerMetadata.http_status;
  const ledgerAttemptValue = state.ledgerConfig?.last_attempts ?? ledgerMetadata.attempts;
  const customerAttemptValue = state.customerConfig?.last_attempts ?? customerMetadata.attempts;
  const ledgerLastError = connectorErrorLabel(
    ledgerErrorCode,
    ledgerRawError,
    ledgerLastRetryable,
  );
  const customerLastError = connectorErrorLabel(
    customerErrorCode,
    customerRawError,
    customerLastRetryable,
  );
  const ledgerGuidance = connectorFixGuidance({
    kind: "ledger",
    connected: ledgerConnected,
    health: ledgerHealth,
    verdict: ledgerLastVerdict,
    errorCode: ledgerErrorCode,
    httpStatus: ledgerHttpStatusValue,
    retryable: ledgerLastRetryable,
  });
  const customerGuidance = connectorFixGuidance({
    kind: "customer",
    connected: customerConnected,
    health: customerHealth,
    verdict: customerLastVerdict,
    errorCode: customerErrorCode,
    httpStatus: customerHttpStatusValue,
    retryable: customerLastRetryable,
  });
  const ledgerPreflight = ledgerPreflightCommand(ledgerForm);
  const customerPreflight = customerPreflightCommand(customerForm);
  const ledgerReadyForPilot = connectorReadyForPilot(
    ledgerConnected,
    ledgerHealth,
    ledgerLastVerdict,
    ledgerErrorCode,
  );
  const customerReadyForPilot = connectorReadyForPilot(
    customerConnected,
    customerHealth,
    customerLastVerdict,
    customerErrorCode,
  );
  const ledgerFailedAttempts = failedPreflightAttempts(ledgerRefundChecks);
  const customerFailedAttempts = failedPreflightAttempts(customerRecordChecks);
  const ledgerRecordPath = state.ledgerConfig?.record_path ?? textValue(ledgerMetadata.record_path);
  const customerRecordPath = state.customerConfig?.record_path ?? textValue(customerMetadata.record_path);
  const ledgerRequestUrl = maskedConnectorUrl(state.ledgerConfig?.base_url ?? ledgerMetadata.request_url);
  const customerRequestUrl = maskedConnectorUrl(state.customerConfig?.base_url ?? customerMetadata.request_url);
  const tokenStatus = state.ledgerConfig?.has_bearer_token
    ? `Stored token ending ${state.ledgerConfig.bearer_token_last4 ?? "****"}`
    : "No bearer token stored";
  const customerTokenStatus = state.customerConfig?.has_bearer_token
    ? `Stored token ending ${state.customerConfig.bearer_token_last4 ?? "****"}`
    : "No bearer token stored";

  function onStartGithubConnect() {
    window.location.href = "/api/zroky/v1/settings/github/connect/start";
  }

  async function copyLedgerPayload() {
    try {
      await navigator.clipboard.writeText(ledgerRefundPayloadSnippet());
      setMessage("Ledger refund saved-connector test payload copied.");
    } catch {
      setMessage("Copy failed. Select the payload and copy it manually.");
    }
  }

  async function copyCustomerPayload() {
    try {
      await navigator.clipboard.writeText(customerRecordPayloadSnippet());
      setMessage("Customer record saved-connector test payload copied.");
    } catch {
      setMessage("Copy failed. Select the payload and copy it manually.");
    }
  }

  async function copyLedgerPreflightCommand() {
    try {
      await navigator.clipboard.writeText(ledgerPreflight);
      setMessage("Ledger refund preflight command copied.");
    } catch {
      setMessage("Copy failed. Select the preflight command and copy it manually.");
    }
  }

  async function copyCustomerPreflightCommand() {
    try {
      await navigator.clipboard.writeText(customerPreflight);
      setMessage("Customer record preflight command copied.");
    } catch {
      setMessage("Copy failed. Select the preflight command and copy it manually.");
    }
  }

  function downloadLedgerTemplate() {
    downloadJsonFile(ledgerConnectorTemplate(ledgerForm), "ledger_refund_connector_config.example.json");
    setMessage("Ledger refund connector template downloaded.");
  }

  function downloadCustomerTemplate() {
    downloadJsonFile(customerConnectorTemplate(customerForm), "customer_record_connector_config.example.json");
    setMessage("Customer record connector template downloaded.");
  }

  function downloadLedgerPreflightSummary() {
    downloadJsonFile(
      buildConnectorPreflightSummary({
        kind: "ledger",
        connected: ledgerConnected,
        health: ledgerHealth,
        verdict: ledgerLastVerdict,
        errorCode: ledgerErrorCode,
        error: ledgerRawError,
        httpStatus: ledgerHttpStatusValue,
        attempts: ledgerAttemptValue,
        retryable: ledgerLastRetryable,
        guidance: ledgerGuidance,
        readyForPilot: ledgerReadyForPilot,
        latestCheck: latestLedgerRefundCheck,
        failedAttempts: ledgerFailedAttempts,
      }),
      "ledger_refund_preflight_summary.json",
    );
    setMessage("Ledger refund preflight summary downloaded.");
  }

  function downloadCustomerPreflightSummary() {
    downloadJsonFile(
      buildConnectorPreflightSummary({
        kind: "customer",
        connected: customerConnected,
        health: customerHealth,
        verdict: customerLastVerdict,
        errorCode: customerErrorCode,
        error: customerRawError,
        httpStatus: customerHttpStatusValue,
        attempts: customerAttemptValue,
        retryable: customerLastRetryable,
        guidance: customerGuidance,
        readyForPilot: customerReadyForPilot,
        latestCheck: latestCustomerRecordCheck,
        failedAttempts: customerFailedAttempts,
      }),
      "customer_record_preflight_summary.json",
    );
    setMessage("Customer record preflight summary downloaded.");
  }

  async function loadConnectorEvidence(check: OutcomeReconciliationView | null, kind: ConnectorEvidenceKind) {
    const label = connectorEvidenceLabel(kind);
    if (!check) {
      setMessage(`${label} evidence pack needs a reconciliation first.`);
      return;
    }
    if (!check.runtime_policy_decision_id) {
      setMessage(`${label} evidence pack is unavailable until the reconciliation is linked to a runtime policy decision.`);
      return;
    }

    setMessage("");
    setEvidenceLoadingFor(check.id);
    try {
      const pack = await getRuntimePolicyEvidencePack(check.runtime_policy_decision_id);
      setConnectorEvidence({ kind, checkId: check.id, pack });
      setMessage(`${label} evidence pack loaded.`);
    } catch (evidenceError) {
      setMessage(evidenceError instanceof Error ? evidenceError.message : `Failed to load ${label.toLowerCase()} evidence pack.`);
    } finally {
      setEvidenceLoadingFor(null);
    }
  }

  function updateLedgerForm(field: keyof LedgerConnectorForm, value: string) {
    setLedgerForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateCustomerForm(field: keyof CustomerConnectorForm, value: string) {
    setCustomerForm((prev) => ({ ...prev, [field]: value }));
  }

  async function onSaveLedgerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setSavingLedger(true);
    try {
      const updated = await saveLedgerRefundConnectorConfig({
        base_url: ledgerForm.baseUrl.trim(),
        path_template: ledgerForm.pathTemplate.trim() || "/refunds/{refund_id}",
        record_path: optionalText(ledgerForm.recordPath),
        bearer_token: optionalText(ledgerForm.bearerToken),
      });
      setState((prev) => ({ ...prev, ledgerConfig: updated }));
      setLedgerForm((prev) => formFromLedgerConfig(updated, { ...prev, bearerToken: "" }));
      setMessage("Ledger refund connector saved.");
    } catch (saveError) {
      setMessage(saveError instanceof Error ? saveError.message : "Failed to save ledger refund connector.");
    } finally {
      setSavingLedger(false);
    }
  }

  async function onSaveCustomerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setSavingCustomer(true);
    try {
      const updated = await saveCustomerRecordConnectorConfig({
        base_url: customerForm.baseUrl.trim(),
        path_template: customerForm.pathTemplate.trim() || "/customers/{customer_id}",
        record_path: optionalText(customerForm.recordPath),
        bearer_token: optionalText(customerForm.bearerToken),
      });
      setState((prev) => ({ ...prev, customerConfig: updated }));
      setCustomerForm((prev) => formFromCustomerConfig(updated, { ...prev, bearerToken: "" }));
      setMessage("Customer record connector saved.");
    } catch (saveError) {
      setMessage(saveError instanceof Error ? saveError.message : "Failed to save customer record connector.");
    } finally {
      setSavingCustomer(false);
    }
  }

  async function onTestLedgerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setTestingLedger(true);
    const refundId = ledgerForm.testRefundId.trim();
    const amountText = ledgerForm.testAmountUsd.trim();
    const amountUsd = amountText ? Number(amountText) : null;
    const claimed: Record<string, unknown> = { refund_id: refundId };
    if (amountUsd !== null && Number.isFinite(amountUsd)) claimed.amount_usd = amountUsd;
    if (ledgerForm.testCurrency.trim()) claimed.currency = ledgerForm.testCurrency.trim().toUpperCase();
    if (ledgerForm.testStatus.trim()) claimed.status = ledgerForm.testStatus.trim();

    try {
      const result = await testLedgerRefundConnector({
        refund_id: refundId,
        claimed,
        amount_usd: amountUsd !== null && Number.isFinite(amountUsd) ? amountUsd : null,
        currency: ledgerForm.testCurrency.trim() ? ledgerForm.testCurrency.trim().toUpperCase() : null,
        match_fields: Object.keys(claimed),
      });
      setState((prev) => ({
        ...prev,
        ledgerConfig: result.connector,
        outcomeChecks: [
          result.check,
          ...prev.outcomeChecks.filter((item) => item.id !== result.check.id),
        ].slice(0, 25),
      }));
      setMessage(`Ledger refund test recorded ${result.check.verdict}.`);
    } catch (testError) {
      setMessage(testError instanceof Error ? testError.message : "Failed to run ledger refund test.");
    } finally {
      setTestingLedger(false);
    }
  }

  async function onTestCustomerConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setTestingCustomer(true);
    const customerId = customerForm.testCustomerId.trim();
    const claimed: Record<string, unknown> = { customer_id: customerId };
    if (customerForm.testEmail.trim()) claimed.email = customerForm.testEmail.trim().toLowerCase();
    if (customerForm.testStatus.trim()) claimed.status = customerForm.testStatus.trim();
    if (customerForm.testAccountId.trim()) claimed.account_id = customerForm.testAccountId.trim();

    try {
      const result = await testCustomerRecordConnector({
        customer_id: customerId,
        claimed,
        match_fields: Object.keys(claimed),
      });
      setState((prev) => ({
        ...prev,
        customerConfig: result.connector,
        outcomeChecks: [
          result.check,
          ...prev.outcomeChecks.filter((item) => item.id !== result.check.id),
        ].slice(0, 25),
      }));
      setMessage(`Customer record test recorded ${result.check.verdict}.`);
    } catch (testError) {
      setMessage(testError instanceof Error ? testError.message : "Failed to run customer record test.");
    } finally {
      setTestingCustomer(false);
    }
  }

  async function onDisconnectGithub() {
    setMessage("");
    try {
      const updated = await disconnectGithubRepoConnection();
      setState((prev) => ({ ...prev, github: updated }));
      setMessage("GitHub connection removed.");
    } catch (disconnectError) {
      setMessage(disconnectError instanceof Error ? disconnectError.message : "Failed to disconnect GitHub.");
    }
  }

  function renderEvidenceControl(check: OutcomeReconciliationView | null, kind: ConnectorEvidenceKind) {
    const label = connectorEvidenceLabel(kind);
    const hasDecision = Boolean(check?.runtime_policy_decision_id);
    const isLoadingEvidence = Boolean(check && evidenceLoadingFor === check.id);

    return (
      <div className="list-row settings-connector-proof-action">
        <div className="list-main">
          <strong>Evidence pack</strong>
          <span>
            {hasDecision
              ? `Decision ${check?.runtime_policy_decision_id} can be exported for audit proof.`
              : "Unavailable until this reconciliation is linked to a runtime policy decision."}
          </span>
        </div>
        <button
          type="button"
          className="btn btn-soft btn-sm"
          disabled={!hasDecision || isLoadingEvidence}
          onClick={() => void loadConnectorEvidence(check, kind)}
        >
          <Download aria-hidden="true" />
          {isLoadingEvidence ? "Loading..." : `View ${label.toLowerCase()} evidence`}
        </button>
      </div>
    );
  }

  function renderEvidenceSummary(check: OutcomeReconciliationView | null, kind: ConnectorEvidenceKind) {
    if (!check || connectorEvidence?.kind !== kind || connectorEvidence.checkId !== check.id) {
      return null;
    }

    const { pack } = connectorEvidence;
    const matched = evidenceMatchedOutcome(pack);

    return (
      <section className="settings-connector-evidence" aria-label={`${connectorEvidenceLabel(kind)} evidence pack`}>
        <div className="settings-connector-evidence-header">
          <div>
            <span className="eyebrow">Evidence Pack</span>
            <h4>{evidenceStatusLabel(pack.verification_status)}</h4>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => downloadConnectorEvidencePack(pack, kind)}
          >
            <Download aria-hidden="true" />
            Download JSON
          </button>
        </div>
        <dl className="settings-connector-evidence-grid">
          <div>
            <dt>Decision</dt>
            <dd>{pack.decision_id}</dd>
          </div>
          <div>
            <dt>Generated</dt>
            <dd>{formatDateTime(pack.generated_at)}</dd>
          </div>
          <div>
            <dt>Matched outcome</dt>
            <dd>{matched?.system_ref ?? "No matched system-of-record outcome is linked yet."}</dd>
          </div>
          <div>
            <dt>Evidence hash</dt>
            <dd>
              <code>{pack.evidence_hash}</code>
            </dd>
          </div>
        </dl>
      </section>
    );
  }

  function renderPreflightSummary(
    kind: ConnectorEvidenceKind,
    readyForPilot: boolean,
    latestCheck: OutcomeReconciliationView | null,
    failedAttempts: OutcomeReconciliationView[],
    onDownload: () => void,
  ) {
    const label = connectorPreflightLabel(kind);
    const status = readyForPilot ? "Ready for pilot handoff" : "Not ready for pilot handoff";

    return (
      <section className="settings-connector-preflight-summary" aria-label={`${label} preflight summary`}>
        <div className="settings-connector-preflight-summary-header">
          <div>
            <span className="eyebrow">Preflight summary</span>
            <strong>{status}</strong>
          </div>
          <span className={readyForPilot ? "pill pill-green" : "pill pill-yellow"}>{status}</span>
        </div>
        <div className="settings-connector-summary-grid">
          <div>
            <span>Latest check</span>
            <strong>{latestCheck?.system_ref ?? "No system-of-record check yet"}</strong>
          </div>
          <div>
            <span>Outcome</span>
            <strong>{connectorStatus(latestCheck)}</strong>
          </div>
          <div>
            <span>Failed attempts</span>
            <strong>{failedAttempts.length ? `${failedAttempts.length} in latest 25` : "None in latest 25"}</strong>
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-soft" onClick={onDownload}>
            <Download aria-hidden="true" />
            Download preflight summary
          </button>
        </div>
      </section>
    );
  }

  function renderFailedPreflightAttempts(kind: ConnectorEvidenceKind, failedAttempts: OutcomeReconciliationView[]) {
    const label = connectorPreflightLabel(kind);

    return (
      <section className="settings-connector-timeline" aria-label={`${label} failed preflight attempts`}>
        <div className="settings-connector-timeline-header">
          <span className="eyebrow">Failed attempts</span>
          <strong>{failedAttempts.length ? `${failedAttempts.length} needs review` : "No failed attempts"}</strong>
        </div>
        {failedAttempts.length ? (
          <ol>
            {failedAttempts.map((check) => (
              <li key={check.id}>
                <div>
                  <strong>
                    {connectorStatus(check)} - {check.system_ref ?? "No system reference"}
                  </strong>
                  <span>{formatDateTime(check.checked_at)}</span>
                  <span>{preflightCheckIssue(check)}</span>
                </div>
                <div className="settings-connector-timeline-meta">
                  <span>{preflightCheckHttpStatus(check)}</span>
                  <span>{preflightCheckAttempts(check)}</span>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p>No failed preflight attempts in the latest 25 checks.</p>
        )}
      </section>
    );
  }

  return (
    <div className="page-content settings-integrations-page">
      {message ? (
        <div className={isProblemMessage(message) ? "alert-strip alert-strip-error" : "alert-strip"}>
          {message}
        </div>
      ) : null}

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>Integrations</h3>
            <p>Connect source control, alert delivery, and system-of-record connectors for outcome proof.</p>
          </div>
          <div className="actions">
            <Link href="/pilot?source=dashboard&intent=connector-proof" className="btn btn-soft">
              <FileJson aria-hidden="true" />
              Pilot handoff
            </Link>
            <button type="button" className="btn btn-soft" onClick={() => void load()} disabled={loading}>
              <RefreshCw aria-hidden="true" />
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </header>
      </section>

      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <GitPullRequest aria-hidden="true" />
          <span>GitHub</span>
          <strong>{githubConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.github?.github_login ? `@${state.github.github_login}` : "Connect GitHub before generated fix PRs."}</small>
        </article>
        <article className="panel settings-summary-card">
          <MessageSquare aria-hidden="true" />
          <span>Slack</span>
          <strong>{slackConnected ? "Connected" : "Not connected"}</strong>
          <small>{state.slack?.channel_name ? `#${state.slack.channel_name}` : "OAuth install required before alerts deliver."}</small>
        </article>
        <article className="panel settings-summary-card">
          <CheckCircle2 aria-hidden="true" />
          <span>Ready</span>
          <strong>{readyCount}/4</strong>
          <small>Connected integrations can create PRs, deliver alerts, or prove outcomes.</small>
        </article>
        <article className="panel settings-summary-card">
          <DatabaseZap aria-hidden="true" />
            <span>Outcome proof</span>
          <strong>{ledgerConnected || customerConnected ? `${Number(Boolean(ledgerVerified)) + Number(Boolean(customerVerified))}/2 verified` : "Not configured"}</strong>
          <small>{ledgerConnected || customerConnected ? `Ledger ${connectorStatus(latestLedgerRefundCheck)} / CRM ${connectorStatus(latestCustomerRecordCheck)}` : "Save a connector before running proof."}</small>
        </article>
      </section>

      <section className="settings-integration-grid">
        <article className="panel settings-integration-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <GitPullRequest aria-hidden="true" />
              <div>
                <h3>GitHub</h3>
                <p>Repository access for generated fix pull requests and source-linked reliability work.</p>
              </div>
            </div>
            <span className={githubConnected ? "pill pill-green" : "pill"}>
              {integrationStatus(githubConnected)}
            </span>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Account</strong>
                <span>{state.github?.github_login ? `@${state.github.github_login}` : "Not connected"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Scopes</strong>
                <span>{state.github?.scopes?.length ? state.github.scopes.join(", ") : "Connect to grant repository access."}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Updated</strong>
                <span>
                  {state.github?.updated_at
                    ? formatDateTime(state.github.updated_at)
                    : state.github?.connected_at
                      ? formatDateTime(state.github.connected_at)
                      : "Waiting for connection"}
                </span>
              </div>
            </div>
          </div>

          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={onStartGithubConnect}>
              {githubConnected ? "Reconnect GitHub" : "Connect GitHub"}
            </button>
            {githubConnected ? (
              <button type="button" className="btn btn-soft" onClick={() => void onDisconnectGithub()}>
                Disconnect
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel settings-integration-card">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <MessageSquare aria-hidden="true" />
              <div>
                <h3>Slack</h3>
                <p>OAuth app install with workspace, channel, scopes, and test-message support.</p>
              </div>
            </div>
            <span className={slackConnected ? "pill pill-green" : "pill"}>
              {integrationStatus(slackConnected)}
            </span>
          </header>

          <div className="list">
            <div className="list-row">
              <div className="list-main">
                <strong>Workspace</strong>
                <span>{state.slack?.team_name ?? state.slack?.team_id ?? "Not connected"}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Channel</strong>
                <span>{state.slack?.channel_name ? `#${state.slack.channel_name}` : state.slack?.channel_id ?? "Not configured"}</span>
              </div>
            </div>
          </div>

          <div className="actions">
            <Link href="/settings/integrations/slack" className="btn btn-primary">
              Manage Slack
            </Link>
          </div>
        </article>

        <article className="panel settings-integration-card settings-connector-card" id="ledger-refund-connector">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <DatabaseZap aria-hidden="true" />
              <div>
                <h3>Ledger refund connector</h3>
                <p>System-of-record proof for refund agents and money-touching workflows.</p>
              </div>
            </div>
            <span className={ledgerConnected ? connectorPillClass(latestLedgerRefundCheck) : "pill"}>
              {ledgerConnected ? connectorStatus(latestLedgerRefundCheck) : "Not configured"}
            </span>
          </header>

          <div className="settings-connector-facts" aria-label="Ledger refund connector status">
            <div>
              <span>Masked endpoint</span>
              <strong>{ledgerRequestUrl}</strong>
            </div>
            <div>
              <span>Health</span>
              <strong>{connectorHealthLabel(ledgerHealth)}</strong>
            </div>
            <div>
              <span>Last verdict</span>
              <strong>{connectorVerdictLabel(ledgerLastVerdict)}</strong>
            </div>
            <div>
              <span>Last error</span>
              <strong>{ledgerLastError}</strong>
            </div>
            <div>
              <span>Last HTTP</span>
              <strong>{textValue(ledgerHttpStatusValue) ?? "No response yet"}</strong>
            </div>
            <div>
              <span>Attempts</span>
              <strong>{textValue(ledgerAttemptValue) ?? "No run yet"}</strong>
            </div>
            <div>
              <span>Record path</span>
              <strong>{ledgerRecordPath ?? "data or data.0"}</strong>
            </div>
            <div>
              <span>Token</span>
              <strong>{tokenStatus}</strong>
            </div>
          </div>

          <section className="settings-connector-guidance" aria-label="Ledger refund preflight guidance">
            <div>
              <span className="eyebrow">Preflight fix</span>
              <strong>{ledgerHealth === "healthy" && ledgerLastVerdict === "matched" ? "Pilot ready" : "Action required"}</strong>
            </div>
            <p>{ledgerGuidance}</p>
          </section>

          <form className="settings-connector-form" onSubmit={(event) => void onSaveLedgerConnector(event)}>
            <div className="settings-connector-form-grid">
              <label>
                <span>Base URL</span>
                <input
                  value={ledgerForm.baseUrl}
                  onChange={(event) => updateLedgerForm("baseUrl", event.target.value)}
                  placeholder="https://ledger.example.com/api"
                  required
                />
              </label>
              <label>
                <span>Path template</span>
                <input
                  value={ledgerForm.pathTemplate}
                  onChange={(event) => updateLedgerForm("pathTemplate", event.target.value)}
                  placeholder="/refunds/{refund_id}"
                  required
                />
              </label>
              <label>
                <span>Record path</span>
                <input
                  value={ledgerForm.recordPath}
                  onChange={(event) => updateLedgerForm("recordPath", event.target.value)}
                  placeholder="data"
                />
              </label>
              <label>
                <span>Bearer token</span>
                <input
                  type="password"
                  value={ledgerForm.bearerToken}
                  onChange={(event) => updateLedgerForm("bearerToken", event.target.value)}
                  placeholder={state.ledgerConfig?.has_bearer_token ? "Paste to rotate stored token" : "Optional bearer token"}
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={savingLedger || !ledgerForm.baseUrl.trim()}>
                <Save aria-hidden="true" />
                {savingLedger ? "Saving..." : "Save connector"}
              </button>
            </div>
          </form>

          <form className="settings-connector-test" onSubmit={(event) => void onTestLedgerConnector(event)}>
            <div className="settings-connector-test-grid">
              <label>
                <span>Refund ID</span>
                <input
                  value={ledgerForm.testRefundId}
                  onChange={(event) => updateLedgerForm("testRefundId", event.target.value)}
                  placeholder="RF-1001"
                  required
                />
              </label>
              <label>
                <span>Amount USD</span>
                <input
                  inputMode="decimal"
                  value={ledgerForm.testAmountUsd}
                  onChange={(event) => updateLedgerForm("testAmountUsd", event.target.value)}
                  placeholder="42.50"
                />
              </label>
              <label>
                <span>Currency</span>
                <input
                  value={ledgerForm.testCurrency}
                  onChange={(event) => updateLedgerForm("testCurrency", event.target.value)}
                  placeholder="USD"
                />
              </label>
              <label>
                <span>Status</span>
                <input
                  value={ledgerForm.testStatus}
                  onChange={(event) => updateLedgerForm("testStatus", event.target.value)}
                  placeholder="posted"
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-soft" disabled={!ledgerConnected || testingLedger || !ledgerForm.testRefundId.trim()}>
                <PlayCircle aria-hidden="true" />
                {testingLedger ? "Running..." : "Run test reconciliation"}
              </button>
            </div>
          </form>

          <section className="settings-connector-handoff" aria-label="Ledger refund pilot handoff">
            <div className="settings-connector-handoff-header">
              <FileJson aria-hidden="true" />
              <div>
                <h4>Pilot preflight handoff</h4>
                <p>demos/design-partner-install-kit/ledger_refund_connector_config.example.json</p>
              </div>
            </div>
            <pre className="settings-connector-payload" aria-label="Ledger refund preflight command">
              <code>{ledgerPreflight}</code>
            </pre>
            <div className="actions">
              <button type="button" className="btn btn-soft" onClick={() => void copyLedgerPreflightCommand()}>
                <Copy aria-hidden="true" />
                Copy preflight command
              </button>
              <button type="button" className="btn btn-soft" onClick={downloadLedgerTemplate}>
                <Download aria-hidden="true" />
                Download template JSON
              </button>
            </div>
          </section>

          {renderPreflightSummary(
            "ledger",
            ledgerReadyForPilot,
            latestLedgerRefundCheck,
            ledgerFailedAttempts,
            downloadLedgerPreflightSummary,
          )}
          {renderFailedPreflightAttempts("ledger", ledgerFailedAttempts)}

          <div className="list settings-connector-proof">
            <div className="list-row">
              <div className="list-main">
                <strong>System reference</strong>
                <span>{latestLedgerRefundCheck?.system_ref ?? "Run the first reconciliation to link a ledger record."}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Last verdict</strong>
                <span>{latestLedgerRefundCheck?.verdict ?? "not_verified"}</span>
              </div>
            </div>
            {renderEvidenceControl(latestLedgerRefundCheck, "ledger")}
          </div>
          {renderEvidenceSummary(latestLedgerRefundCheck, "ledger")}

          <pre className="settings-connector-payload" aria-label="Ledger refund saved connector test payload">
            <code>{ledgerRefundPayloadSnippet()}</code>
          </pre>

          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void copyLedgerPayload()}>
              <Copy aria-hidden="true" />
              Copy saved test payload
            </button>
            <Link href="/outcomes" className="btn btn-primary">
              View outcome checks
            </Link>
          </div>
        </article>

        <article className="panel settings-integration-card settings-connector-card" id="customer-record-connector">
          <header className="panel-header">
            <div className="settings-card-title-row">
              <DatabaseZap aria-hidden="true" />
              <div>
                <h3>Customer record connector</h3>
                <p>System-of-record proof for CRM agents that update customer, account, or contact records.</p>
              </div>
            </div>
            <span className={customerConnected ? connectorPillClass(latestCustomerRecordCheck) : "pill"}>
              {customerConnected ? connectorStatus(latestCustomerRecordCheck) : "Not configured"}
            </span>
          </header>

          <div className="settings-connector-facts" aria-label="Customer record connector status">
            <div>
              <span>Masked endpoint</span>
              <strong>{customerRequestUrl}</strong>
            </div>
            <div>
              <span>Health</span>
              <strong>{connectorHealthLabel(customerHealth)}</strong>
            </div>
            <div>
              <span>Last verdict</span>
              <strong>{connectorVerdictLabel(customerLastVerdict)}</strong>
            </div>
            <div>
              <span>Last error</span>
              <strong>{customerLastError}</strong>
            </div>
            <div>
              <span>Last HTTP</span>
              <strong>{textValue(customerHttpStatusValue) ?? "No response yet"}</strong>
            </div>
            <div>
              <span>Attempts</span>
              <strong>{textValue(customerAttemptValue) ?? "No run yet"}</strong>
            </div>
            <div>
              <span>Record path</span>
              <strong>{customerRecordPath ?? "data or records.0"}</strong>
            </div>
            <div>
              <span>Token</span>
              <strong>{customerTokenStatus}</strong>
            </div>
          </div>

          <section className="settings-connector-guidance" aria-label="Customer record preflight guidance">
            <div>
              <span className="eyebrow">Preflight fix</span>
              <strong>{customerHealth === "healthy" && customerLastVerdict === "matched" ? "Pilot ready" : "Action required"}</strong>
            </div>
            <p>{customerGuidance}</p>
          </section>

          <form className="settings-connector-form" onSubmit={(event) => void onSaveCustomerConnector(event)}>
            <div className="settings-connector-form-grid">
              <label>
                <span>CRM base URL</span>
                <input
                  value={customerForm.baseUrl}
                  onChange={(event) => updateCustomerForm("baseUrl", event.target.value)}
                  placeholder="https://crm.example.com/api"
                  required
                />
              </label>
              <label>
                <span>CRM path template</span>
                <input
                  value={customerForm.pathTemplate}
                  onChange={(event) => updateCustomerForm("pathTemplate", event.target.value)}
                  placeholder="/customers/{customer_id}"
                  required
                />
              </label>
              <label>
                <span>CRM record path</span>
                <input
                  value={customerForm.recordPath}
                  onChange={(event) => updateCustomerForm("recordPath", event.target.value)}
                  placeholder="data"
                />
              </label>
              <label>
                <span>CRM bearer token</span>
                <input
                  type="password"
                  value={customerForm.bearerToken}
                  onChange={(event) => updateCustomerForm("bearerToken", event.target.value)}
                  placeholder={state.customerConfig?.has_bearer_token ? "Paste to rotate stored token" : "Optional bearer token"}
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={savingCustomer || !customerForm.baseUrl.trim()}>
                <Save aria-hidden="true" />
                {savingCustomer ? "Saving..." : "Save CRM connector"}
              </button>
            </div>
          </form>

          <form className="settings-connector-test" onSubmit={(event) => void onTestCustomerConnector(event)}>
            <div className="settings-connector-test-grid">
              <label>
                <span>Customer ID</span>
                <input
                  value={customerForm.testCustomerId}
                  onChange={(event) => updateCustomerForm("testCustomerId", event.target.value)}
                  placeholder="CUS-1001"
                  required
                />
              </label>
              <label>
                <span>Email</span>
                <input
                  value={customerForm.testEmail}
                  onChange={(event) => updateCustomerForm("testEmail", event.target.value)}
                  placeholder="owner@example.com"
                />
              </label>
              <label>
                <span>Status</span>
                <input
                  value={customerForm.testStatus}
                  onChange={(event) => updateCustomerForm("testStatus", event.target.value)}
                  placeholder="active"
                />
              </label>
              <label>
                <span>Account ID</span>
                <input
                  value={customerForm.testAccountId}
                  onChange={(event) => updateCustomerForm("testAccountId", event.target.value)}
                  placeholder="acct_1001"
                />
              </label>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-soft" disabled={!customerConnected || testingCustomer || !customerForm.testCustomerId.trim()}>
                <PlayCircle aria-hidden="true" />
                {testingCustomer ? "Running..." : "Run CRM test reconciliation"}
              </button>
            </div>
          </form>

          <section className="settings-connector-handoff" aria-label="Customer record pilot handoff">
            <div className="settings-connector-handoff-header">
              <FileJson aria-hidden="true" />
              <div>
                <h4>Pilot preflight handoff</h4>
                <p>demos/design-partner-install-kit/customer_record_connector_config.example.json</p>
              </div>
            </div>
            <pre className="settings-connector-payload" aria-label="Customer record preflight command">
              <code>{customerPreflight}</code>
            </pre>
            <div className="actions">
              <button type="button" className="btn btn-soft" onClick={() => void copyCustomerPreflightCommand()}>
                <Copy aria-hidden="true" />
                Copy preflight command
              </button>
              <button type="button" className="btn btn-soft" onClick={downloadCustomerTemplate}>
                <Download aria-hidden="true" />
                Download template JSON
              </button>
            </div>
          </section>

          {renderPreflightSummary(
            "customer",
            customerReadyForPilot,
            latestCustomerRecordCheck,
            customerFailedAttempts,
            downloadCustomerPreflightSummary,
          )}
          {renderFailedPreflightAttempts("customer", customerFailedAttempts)}

          <div className="list settings-connector-proof">
            <div className="list-row">
              <div className="list-main">
                <strong>System reference</strong>
                <span>{latestCustomerRecordCheck?.system_ref ?? "Run the first reconciliation to link a CRM record."}</span>
              </div>
            </div>
            <div className="list-row">
              <div className="list-main">
                <strong>Last verdict</strong>
                <span>{latestCustomerRecordCheck?.verdict ?? "not_verified"}</span>
              </div>
            </div>
            {renderEvidenceControl(latestCustomerRecordCheck, "customer")}
          </div>
          {renderEvidenceSummary(latestCustomerRecordCheck, "customer")}

          <pre className="settings-connector-payload" aria-label="Customer record saved connector test payload">
            <code>{customerRecordPayloadSnippet()}</code>
          </pre>

          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void copyCustomerPayload()}>
              <Copy aria-hidden="true" />
              Copy CRM saved test payload
            </button>
            <Link href="/outcomes" className="btn btn-primary">
              View outcome checks
            </Link>
          </div>
        </article>

      </section>

    </div>
  );
}
