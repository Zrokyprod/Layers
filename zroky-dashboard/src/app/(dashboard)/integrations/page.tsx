"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Copy,
  DatabaseZap,
  FileJson,
  Plug,
  PlayCircle,
  RadioTower,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react";

import {
  getGenericRestConnectorStatus,
  getCustomerRecordConnectorStatus,
  getGithubConnectionStatus,
  getLedgerRefundConnectorStatus,
  getSlackInstallStatus,
  getToolRegistry,
  listOutcomeReconciliations,
  saveGenericRestConnectorConfig,
  testGenericRestConnector,
  type CustomerRecordConnectorStatusResponse,
  type GenericRestConnectorStatusResponse,
  type LedgerRefundConnectorStatusResponse,
  type OutcomeReconciliationView,
  type ToolImplementationStatus,
  type ToolRegistryItemResponse,
  type ToolRegistryResponse,
} from "@/lib/api";
import SystemOfRecordConnectors from "./system-of-record-connectors";
import type {
  GithubConnectionStatusResponse,
  SlackInstallStatusResponse,
} from "@/lib/types";

type ConnectorsOverviewState = {
  github: GithubConnectionStatusResponse | null;
  slack: SlackInstallStatusResponse | null;
  ledger: LedgerRefundConnectorStatusResponse | null;
  customer: CustomerRecordConnectorStatusResponse | null;
  generic: GenericRestConnectorStatusResponse | null;
  checks: OutcomeReconciliationView[];
  registry: ToolRegistryResponse | null;
};

type SystemConnectorStatus =
  | LedgerRefundConnectorStatusResponse
  | CustomerRecordConnectorStatusResponse
  | GenericRestConnectorStatusResponse;

type GenericRestFormState = {
  baseUrl: string;
  pathTemplate: string;
  recordPath: string;
  bearerToken: string;
  recordRef: string;
  actionType: string;
  claimedJson: string;
  matchFieldsText: string;
};

type ConnectorSummary = {
  href: string;
  label: string;
  title: string;
  status: string;
  detail: string;
  cta: string;
  tone: "danger" | "neutral" | "success" | "warning";
};

const initialOverview: ConnectorsOverviewState = {
  github: null,
  slack: null,
  ledger: null,
  customer: null,
  generic: null,
  checks: [],
  registry: null,
};

const defaultGenericRestForm: GenericRestFormState = {
  baseUrl: "",
  pathTemplate: "/records/{record_ref}",
  recordPath: "data",
  bearerToken: "",
  recordRef: "record_1001",
  actionType: "internal_api_mutation",
  claimedJson: JSON.stringify(
    {
      record_ref: "record_1001",
      status: "approved",
    },
    null,
    2,
  ),
  matchFieldsText: "status",
};

function isLedgerRefundCheck(item: OutcomeReconciliationView) {
  const metadata = item.metadata && typeof item.metadata === "object" && !Array.isArray(item.metadata)
    ? item.metadata as Record<string, unknown>
    : {};
  return item.connector_type === "ledger_refund_api" || metadata.connector_kind === "ledger_refund_api";
}

function isCustomerRecordCheck(item: OutcomeReconciliationView) {
  const metadata = item.metadata && typeof item.metadata === "object" && !Array.isArray(item.metadata)
    ? item.metadata as Record<string, unknown>
    : {};
  return item.connector_type === "customer_record_api" || metadata.connector_kind === "customer_record_api";
}

function isGenericRestCheck(item: OutcomeReconciliationView) {
  const metadata = item.metadata && typeof item.metadata === "object" && !Array.isArray(item.metadata)
    ? item.metadata as Record<string, unknown>
    : {};
  return item.connector_type === "generic_rest_api" || metadata.connector_kind === "generic_rest_api";
}

function formatConnectorLabel(value: string | null | undefined) {
  if (!value) return "Not verified";
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function connectorReady(
  connector: SystemConnectorStatus | null,
  latestCheck: OutcomeReconciliationView | null,
) {
  return Boolean(
    connector?.connected
      && connector.health_status === "healthy"
      && (connector.last_verdict ?? latestCheck?.verdict) === "matched"
      && connector.readiness?.status === "ready"
      && !connector.last_error_code,
  );
}

function connectorNeedsProof(
  connector: SystemConnectorStatus | null,
  latestCheck: OutcomeReconciliationView | null,
) {
  return Boolean(connector?.connected && !connectorReady(connector, latestCheck));
}

function connectorSummary({
  connector,
  cta,
  href,
  label,
  latestCheck,
  title,
}: {
  connector: SystemConnectorStatus | null;
  cta: string;
  href: string;
  label: string;
  latestCheck: OutcomeReconciliationView | null;
  title: string;
}): ConnectorSummary {
  const ready = connectorReady(connector, latestCheck);
  const connected = Boolean(connector?.connected);
  const verdict = connector?.last_verdict ?? latestCheck?.verdict ?? null;
  const readiness = connector?.readiness?.status ?? "not_ready";
  const error = connector?.last_error_code ?? null;

  if (!connected) {
    return {
      href,
      label,
      title,
      status: "Not configured",
      detail: "Save a read-scoped system-of-record connector before this action can produce buyer proof.",
      cta,
      tone: "warning",
    };
  }
  if (ready && connector) {
    return {
      href,
      label,
      title,
      status: "Ready",
      detail: `${formatConnectorLabel(connector.health_status)} / ${formatConnectorLabel(verdict)} / evidence exportable.`,
      cta,
      tone: "success",
    };
  }
  if (error || verdict === "mismatched") {
    return {
      href,
      label,
      title,
      status: "Blocked",
      detail: error
        ? `${formatConnectorLabel(error)} is blocking preflight.`
        : "Latest proof mismatched the system of record.",
      cta,
      tone: "danger",
    };
  }
  return {
    href,
    label,
    title,
    status: "Needs preflight",
    detail: `${formatConnectorLabel(readiness)} / ${formatConnectorLabel(verdict)}. Run saved proof before handoff.`,
    cta,
    tone: "warning",
  };
}

function toolStatusTone(status: ToolImplementationStatus): ConnectorSummary["tone"] {
  if (status === "available") return "success";
  if (status === "template") return "warning";
  return "neutral";
}

function toolStatusLabel(status: ToolImplementationStatus) {
  if (status === "available") return "Available now";
  if (status === "template") return "Template";
  return "Planned";
}

function formatRegistryCategory(value: string) {
  return value.replace(/_/g, " ");
}

function registryItems(registry: ToolRegistryResponse | null) {
  if (!registry) return [];
  return [
    ...registry.runtime_paths,
    ...registry.verification_connectors,
    ...registry.native_tool_families,
  ];
}

function registryStatusCount(registry: ToolRegistryResponse | null, status: ToolImplementationStatus) {
  return registryItems(registry).filter((item) => item.implementation_status === status).length;
}

function labelsForStatus(items: ToolRegistryItemResponse[], status: ToolImplementationStatus) {
  return items
    .filter((item) => item.implementation_status === status)
    .map((item) => item.label);
}

function compactLabelList(labels: string[], fallback: string) {
  if (labels.length === 0) return fallback;
  if (labels.length <= 3) return labels.join(", ");
  return `${labels.slice(0, 3).join(", ")} +${labels.length - 3} more`;
}

function ConnectorRegistryItem({ item }: { item: ToolRegistryItemResponse }) {
  const content = (
    <>
      <div className="connectors-registry-item-head">
        <h3>{item.label}</h3>
        <span className="connectors-registry-status" data-tone={toolStatusTone(item.implementation_status)}>
          {toolStatusLabel(item.implementation_status)}
        </span>
      </div>
      <p>{item.description}</p>
      <div className="connectors-registry-meta">
        <span>{formatRegistryCategory(item.category)}</span>
        {item.requires_customer_credentials ? <span>customer credentials</span> : null}
        {item.backend_capability ? <span>{item.backend_capability}</span> : null}
      </div>
    </>
  );

  if (!item.dashboard_href) {
    return <article className="connectors-registry-item">{content}</article>;
  }

  return (
    <Link href={item.dashboard_href} className="connectors-registry-item">
      {content}
    </Link>
  );
}

function ConnectorRegistryCatalog({
  loading,
  registry,
}: {
  loading: boolean;
  registry: ToolRegistryResponse | null;
}) {
  const groups = registry
    ? [
        {
          label: "Runtime paths",
          helper: "Where Zroky sits before an agent action.",
          items: registry.runtime_paths,
        },
        {
          label: "Proof verifiers",
          helper: "Systems that can prove the real-world outcome.",
          items: registry.verification_connectors,
        },
        {
          label: "Native tool templates",
          helper: "Convenience adapters for common agent tools.",
          items: registry.native_tool_families,
        },
      ]
    : [];
  const liveVerifierLabels = registry
    ? labelsForStatus(registry.verification_connectors, "available")
    : [];
  const plannedNativeLabels = registry
    ? labelsForStatus(registry.native_tool_families, "planned")
    : [];

  return (
    <section className="panel connectors-registry-panel" aria-label="Phase 1 connector catalog">
      <div className="connectors-registry-head">
        <div>
          <span className="eyebrow">Phase 1 catalog</span>
          <h2>Connector coverage</h2>
          <p>Available now means usable in the current product. Template means generic setup exists. Planned means native coverage is visible but not ready to sell yet.</p>
        </div>
        <div className="connectors-registry-counts" aria-label="Connector implementation status">
          <span data-tone="success">{registryStatusCount(registry, "available")} available now</span>
          <span data-tone="warning">{registryStatusCount(registry, "template")} template</span>
          <span>{registryStatusCount(registry, "planned")} planned</span>
        </div>
      </div>

      {registry ? (
        <>
          <div className="connectors-truth-strip" aria-label="Connector launch truth">
            <div>
              <span>Live proof connectors</span>
              <strong>{compactLabelList(liveVerifierLabels, "No live proof verifier")}</strong>
              <small>These can produce matched, mismatched, or not_verified outcome checks now.</small>
            </div>
            <div>
              <span>Fallback path</span>
              <strong>Generic REST/OpenAPI verifier</strong>
              <small>Use this for unsupported Stripe, Razorpay, Zendesk, Gmail, HubSpot, Salesforce, and internal tools.</small>
            </div>
            <div>
              <span>Planned native adapters</span>
              <strong>{compactLabelList(plannedNativeLabels, "No planned native adapters")}</strong>
              <small>Native convenience connectors stay planned until they have real proof wiring.</small>
            </div>
          </div>

          <div className="connectors-registry-groups">
            {groups.map((group) => (
              <section className="connectors-registry-group" key={group.label} aria-label={group.label}>
                <div className="connectors-registry-group-head">
                  <strong>{group.label}</strong>
                  <span>{group.helper}</span>
                </div>
                <div className="connectors-registry-grid">
                  {group.items.map((item) => (
                    <ConnectorRegistryItem key={item.id} item={item} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </>
      ) : (
        <div className="connectors-registry-empty">
          <strong>{loading ? "Loading connector catalog" : "Connector catalog unavailable"}</strong>
          <span>{loading ? "Syncing tool coverage from the backend registry." : "Refresh after the backend registry is reachable."}</span>
        </div>
      )}
    </section>
  );
}

function parseClaimedJson(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Claimed JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function matchFieldsFromText(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function safeClaimedJson(value: string, recordRef: string): Record<string, unknown> {
  try {
    return parseClaimedJson(value);
  } catch {
    return {
      record_ref: recordRef,
      status: "approved",
    };
  }
}

function buildGenericRestBridgePayload(form: GenericRestFormState) {
  const recordRef = form.recordRef.trim() || "record_1001";
  const payload = {
    connector: "generic_rest",
    record_ref: recordRef,
    action_type: form.actionType.trim() || "internal_api_mutation",
    claimed: safeClaimedJson(form.claimedJson, recordRef),
    match_fields: matchFieldsFromText(form.matchFieldsText),
    metadata: {
      runtime_path: "webhook_bridge",
      setup_source: "generic_rest_connector_setup",
    },
  };

  return JSON.stringify(payload, null, 2);
}

function buildGenericRestBridgeCurl(form: GenericRestFormState) {
  return `curl -X POST "https://api.zroky.com/v1/outcomes/reconciliation/saved" \\
  -H "content-type: application/json" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  --data '${buildGenericRestBridgePayload(form)}'`;
}

function GenericRestSetupPanel({
  status,
  latestCheck,
  onStatusChange,
}: {
  status: GenericRestConnectorStatusResponse | null;
  latestCheck: OutcomeReconciliationView | null;
  onStatusChange: (status: GenericRestConnectorStatusResponse) => void;
}) {
  const [form, setForm] = useState<GenericRestFormState>(defaultGenericRestForm);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [copiedBridge, setCopiedBridge] = useState(false);
  const readiness = status?.readiness?.status ?? "not_ready";
  const connected = Boolean(status?.connected);
  const latestVerdict = status?.last_verdict ?? latestCheck?.verdict ?? "No run yet";
  const bridgeCurl = buildGenericRestBridgeCurl(form);

  useEffect(() => {
    if (!status?.connected) return;
    setForm((prev) => ({
      ...prev,
      baseUrl: status.base_url ?? prev.baseUrl,
      pathTemplate: status.path_template ?? prev.pathTemplate,
      recordPath: status.record_path ?? prev.recordPath,
    }));
  }, [status?.base_url, status?.connected, status?.path_template, status?.record_path]);

  const updateForm = (field: keyof GenericRestFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setSaving(true);
    try {
      const updated = await saveGenericRestConnectorConfig({
        base_url: form.baseUrl.trim(),
        path_template: form.pathTemplate.trim() || "/records/{record_ref}",
        record_path: form.recordPath.trim() || null,
        bearer_token: form.bearerToken.trim() || null,
      });
      onStatusChange(updated);
      setForm((prev) => ({ ...prev, bearerToken: "" }));
      setMessage("Generic REST verifier saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save Generic REST verifier.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setTesting(true);
    try {
      const claimed = parseClaimedJson(form.claimedJson);
      const result = await testGenericRestConnector({
        record_ref: form.recordRef.trim(),
        action_type: form.actionType.trim() || "custom",
        claimed,
        match_fields: matchFieldsFromText(form.matchFieldsText),
      });
      onStatusChange(result.connector);
      setMessage(`Generic REST test recorded ${result.check.verdict}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to run Generic REST proof test.");
    } finally {
      setTesting(false);
    }
  };

  const copyBridge = async () => {
    try {
      await navigator.clipboard.writeText(bridgeCurl);
      setCopiedBridge(true);
      window.setTimeout(() => setCopiedBridge(false), 2000);
    } catch {
      setMessage("Copy failed. Select the bridge request and copy it manually.");
    }
  };

  return (
    <section className="panel connectors-generic-panel" id="generic-rest-connector" aria-label="Generic REST verifier setup">
      <div className="connectors-generic-head">
        <div>
          <span className="eyebrow">Custom systems</span>
          <h2>Generic REST/OpenAPI verifier</h2>
          <p>Use this for internal tools, custom CRMs, billing systems, workflow APIs, and any agent action with a readable JSON outcome.</p>
        </div>
        <div className="connectors-generic-status">
          <span>{connected ? "Configured" : "Not configured"}</span>
          <strong>{connectorReady(status, latestCheck) ? "Ready" : formatConnectorLabel(readiness)}</strong>
          <small>{formatConnectorLabel(String(latestVerdict))}</small>
        </div>
      </div>

      {message ? <div className="connectors-generic-message">{message}</div> : null}

      <div className="connectors-generic-layout">
        <form className="connectors-generic-form" onSubmit={saveConfig}>
          <div className="connectors-generic-form-head">
            <strong>1. Save read endpoint</strong>
            <span>HTTPS JSON read only</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Base URL</span>
              <input
                value={form.baseUrl}
                onChange={(event) => updateForm("baseUrl", event.target.value)}
                placeholder="https://api.company.com"
                required
              />
            </label>
            <label>
              <span>Path template</span>
              <input
                value={form.pathTemplate}
                onChange={(event) => updateForm("pathTemplate", event.target.value)}
                placeholder="/orders/{record_ref}"
                required
              />
            </label>
            <label>
              <span>Record path</span>
              <input
                value={form.recordPath}
                onChange={(event) => updateForm("recordPath", event.target.value)}
                placeholder="data"
              />
            </label>
            <label>
              <span>Bearer token</span>
              <input
                value={form.bearerToken}
                onChange={(event) => updateForm("bearerToken", event.target.value)}
                placeholder={status?.has_bearer_token ? "Token saved" : "Read-scoped token"}
                type="password"
              />
            </label>
          </div>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            <Save aria-hidden="true" />
            {saving ? "Saving..." : "Save verifier"}
          </button>
        </form>

        <form className="connectors-generic-form" onSubmit={runTest}>
          <div className="connectors-generic-form-head">
            <strong>2. Run proof test</strong>
            <span>Compare claimed fields to the real record</span>
          </div>
          <div className="connectors-generic-grid">
            <label>
              <span>Record ref</span>
              <input
                value={form.recordRef}
                onChange={(event) => updateForm("recordRef", event.target.value)}
                placeholder="ord_1001"
                required
              />
            </label>
            <label>
              <span>Action type</span>
              <input
                value={form.actionType}
                onChange={(event) => updateForm("actionType", event.target.value)}
                placeholder="internal_api_mutation"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Match fields</span>
              <input
                value={form.matchFieldsText}
                onChange={(event) => updateForm("matchFieldsText", event.target.value)}
                placeholder="status, amount_usd"
              />
            </label>
            <label className="connectors-generic-wide">
              <span>Claimed JSON</span>
              <textarea
                value={form.claimedJson}
                onChange={(event) => updateForm("claimedJson", event.target.value)}
                rows={7}
              />
            </label>
          </div>
          <button type="submit" className="btn btn-soft" disabled={testing || !connected}>
            <PlayCircle aria-hidden="true" />
            {testing ? "Testing..." : "Run proof test"}
          </button>
        </form>

        <article className="connectors-generic-bridge" aria-label="Generic REST webhook bridge request">
          <div className="connectors-generic-form-head">
            <strong>3. Copy webhook bridge request</strong>
            <span>For agents that cannot install the SDK</span>
          </div>
          <p>
            Call this after the agent says the action succeeded. Zroky uses the saved Generic REST connector to verify the real record.
          </p>
          <pre aria-label="Generic REST saved connector bridge curl">
            <code>{bridgeCurl}</code>
          </pre>
          <button type="button" className="btn btn-soft" onClick={() => void copyBridge()}>
            <Copy aria-hidden="true" />
            {copiedBridge ? "Copied" : "Copy bridge request"}
          </button>
        </article>
      </div>
    </section>
  );
}

export default function IntegrationsPage() {
  const [overview, setOverview] = useState<ConnectorsOverviewState>(initialOverview);
  const [loading, setLoading] = useState(true);
  const [partialFailure, setPartialFailure] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    const [githubResult, slackResult, ledgerResult, customerResult, genericResult, checksResult, registryResult] = await Promise.allSettled([
      getGithubConnectionStatus(),
      getSlackInstallStatus(),
      getLedgerRefundConnectorStatus(),
      getCustomerRecordConnectorStatus(),
      getGenericRestConnectorStatus(),
      listOutcomeReconciliations({ limit: 25 }),
      getToolRegistry(),
    ]);

    setOverview({
      github: githubResult.status === "fulfilled" ? githubResult.value : null,
      slack: slackResult.status === "fulfilled" ? slackResult.value : null,
      ledger: ledgerResult.status === "fulfilled" ? ledgerResult.value : null,
      customer: customerResult.status === "fulfilled" ? customerResult.value : null,
      generic: genericResult.status === "fulfilled" ? genericResult.value : null,
      checks: checksResult.status === "fulfilled" ? checksResult.value.items : [],
      registry: registryResult.status === "fulfilled" ? registryResult.value : null,
    });
    setPartialFailure([githubResult, slackResult, ledgerResult, customerResult, genericResult, checksResult, registryResult].some((result) => result.status === "rejected"));
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const ledgerCheck = useMemo(() => overview.checks.find(isLedgerRefundCheck) ?? null, [overview.checks]);
  const customerCheck = useMemo(() => overview.checks.find(isCustomerRecordCheck) ?? null, [overview.checks]);
  const genericCheck = useMemo(() => overview.checks.find(isGenericRestCheck) ?? null, [overview.checks]);
  const ledgerReady = connectorReady(overview.ledger, ledgerCheck);
  const customerReady = connectorReady(overview.customer, customerCheck);
  const genericReady = connectorReady(overview.generic, genericCheck);
  const proofReadyCount = Number(ledgerReady) + Number(customerReady) + Number(genericReady);
  const needsProofCount =
    Number(connectorNeedsProof(overview.ledger, ledgerCheck)) +
    Number(connectorNeedsProof(overview.customer, customerCheck)) +
    Number(connectorNeedsProof(overview.generic, genericCheck));
  const configuredProofCount =
    Number(Boolean(overview.ledger?.connected)) +
    Number(Boolean(overview.customer?.connected)) +
    Number(Boolean(overview.generic?.connected));
  const supportConnectedCount = Number(Boolean(overview.github?.connected)) + Number(Boolean(overview.slack?.connected));
  const matchedChecks = overview.checks.filter((check) => check.verdict === "matched").length;
  const blockedProof = Boolean(
    overview.ledger?.last_error_code
      || overview.customer?.last_error_code
      || overview.generic?.last_error_code
      || ledgerCheck?.verdict === "mismatched"
      || customerCheck?.verdict === "mismatched"
      || genericCheck?.verdict === "mismatched",
  );
  const heroTone = partialFailure || blockedProof
    ? "danger"
    : proofReadyCount === 3
      ? "success"
      : configuredProofCount > 0
        ? "warning"
        : "neutral";
  const heroTitle = partialFailure
    ? "Connector status unavailable"
    : blockedProof
      ? "Proof connector blocked"
      : proofReadyCount === 3
        ? "Systems of record ready"
        : configuredProofCount > 0
          ? "Proof connectors need preflight"
          : "Connect systems of record";
  const heroBadge = loading ? "Syncing" : heroTone === "success" ? "Ready" : heroTone === "danger" ? "Blocked" : "Setup";
  const heroCopy = proofReadyCount === 3
    ? "Ledger, customer record, and generic REST systems can now produce matched outcome proof and export Evidence Packs."
    : "Connect read-scoped source systems, run saved proof, and keep customer evidence exportable before pilot handoff.";
  const connectorCards = [
    connectorSummary({
      connector: overview.ledger,
      cta: "Configure ledger",
      href: "/integrations#ledger-refund-connector",
      label: "Money action proof",
      latestCheck: ledgerCheck,
      title: "Ledger refund",
    }),
    connectorSummary({
      connector: overview.customer,
      cta: "Configure CRM",
      href: "/integrations#customer-record-connector",
      label: "Record mutation proof",
      latestCheck: customerCheck,
      title: "Customer record",
    }),
    connectorSummary({
      connector: overview.generic,
      cta: "Configure Generic REST",
      href: "/integrations#generic-rest-connector",
      label: "Custom tool proof",
      latestCheck: genericCheck,
      title: "Generic REST",
    }),
    {
      href: "/policies",
      label: "Change control",
      title: "GitHub",
      status: overview.github?.connected ? "Connected" : "Not connected",
      detail: overview.github?.github_login ? `@${overview.github.github_login} can support generated fix PRs.` : "Connect repository access before fix proof can gate changes.",
      cta: "Open policies",
      tone: overview.github?.connected ? "success" : "neutral",
    } satisfies ConnectorSummary,
    {
      href: "/integrations/slack",
      label: "Ops delivery",
      title: "Slack",
      status: overview.slack?.connected ? "Connected" : "Not connected",
      detail: overview.slack?.channel_name ? `Alerts route to #${overview.slack.channel_name}.` : "Connect the operating channel for failures, replay, CI, and policy events.",
      cta: "Manage Slack",
      tone: overview.slack?.connected ? "success" : "neutral",
    } satisfies ConnectorSummary,
  ];

  return (
    <div className="dashboard-page integrations-page">
      <section className="page-header connectors-hero" data-tone={heroTone}>
        <div className="connectors-hero-copy">
          <span className="eyebrow">System-of-record proof</span>
          <h1>{heroTitle}</h1>
          <p>{heroCopy}</p>
        </div>
        <div className="connectors-hero-rail">
          <span className="connectors-verdict-pill">{heroBadge}</span>
          <div className="connectors-proof-meter" aria-label="System-of-record readiness">
            <span>Proof ready</span>
            <strong>{proofReadyCount}/3</strong>
            <small>{matchedChecks} matched checks / {needsProofCount} need action</small>
          </div>
        </div>
        <div className="actions connectors-hero-actions">
          <button type="button" className="btn btn-soft" onClick={() => void loadOverview()} disabled={loading}>
            <RefreshCw aria-hidden="true" />
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <Link href="/evidence" className="btn btn-primary">
            Open evidence
          </Link>
        </div>
      </section>

      <section className="connectors-metric-grid" aria-label="Connector readiness">
        <article className="panel connectors-metric-card" data-tone={proofReadyCount === 3 ? "success" : "warning"}>
          <ShieldCheck aria-hidden="true" />
          <span>Proof connectors</span>
          <strong>{proofReadyCount}/3</strong>
          <small>Ledger, CRM, and Generic REST cover core proof paths.</small>
        </article>
        <article className="panel connectors-metric-card">
          <DatabaseZap aria-hidden="true" />
          <span>Configured</span>
          <strong>{configuredProofCount}/3</strong>
          <small>Read-scoped system-of-record connectors saved.</small>
        </article>
        <article className="panel connectors-metric-card" data-tone={needsProofCount > 0 ? "warning" : "success"}>
          <RadioTower aria-hidden="true" />
          <span>Needs action</span>
          <strong>{needsProofCount}</strong>
          <small>Configured connectors that still need matched proof.</small>
        </article>
        <article className="panel connectors-metric-card">
          <Plug aria-hidden="true" />
          <span>Support links</span>
          <strong>{supportConnectedCount}/2</strong>
          <small>GitHub for change proof, Slack for operations delivery.</small>
        </article>
      </section>

      <div className="connectors-workspace">
        <section className="panel connectors-command-panel">
          <div>
            <span className="eyebrow">Decision path</span>
            <h2>Get connector proof to handoff</h2>
            <p>Every customer-facing proof pack depends on a runtime decision linked to a matched system-of-record check.</p>
          </div>
          <div className="connectors-action-chain" aria-label="Connector proof chain">
            <Link href="/integrations#ledger-refund-connector">Configure source system</Link>
            <Link href="/integrations#ledger-refund-connector">Run saved proof</Link>
            <Link href="/outcomes">Review reconciliation</Link>
            <Link href="/evidence">Export Evidence Pack</Link>
          </div>
        </section>

        <section className="connectors-source-grid" aria-label="Connector source status">
          {connectorCards.map((card) => (
            <article className="panel connector-source-card" data-tone={card.tone} key={card.title}>
              <span>{card.label}</span>
              <div>
                <h3>{card.title}</h3>
                <strong>{card.status}</strong>
              </div>
              <p>{card.detail}</p>
              <Link href={card.href} className="btn btn-soft btn-sm">{card.cta}</Link>
            </article>
          ))}
        </section>
      </div>

      <ConnectorRegistryCatalog registry={overview.registry} loading={loading} />

      <GenericRestSetupPanel
        status={overview.generic}
        latestCheck={genericCheck}
        onStatusChange={(generic) => setOverview((prev) => ({ ...prev, generic }))}
      />

      {partialFailure ? (
        <div className="alert-strip connectors-alert">
          <AlertTriangle aria-hidden="true" />
          Some connector status checks could not load. Detailed setup below may show the failing source.
        </div>
      ) : null}

      <section className="connectors-detail-section" aria-label="Connector setup and proof controls">
        <header className="connectors-section-head">
          <div>
            <span className="eyebrow">Operator setup</span>
            <h2>System-of-record connectors</h2>
            <p>Save read-scoped endpoints, run preflight, download summaries, and expose linked Evidence Packs.</p>
          </div>
          <FileJson aria-hidden="true" />
        </header>
        <SystemOfRecordConnectors />
      </section>
    </div>
  );
}
