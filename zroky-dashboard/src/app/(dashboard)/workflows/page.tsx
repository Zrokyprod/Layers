"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Database, FileJson, GitBranch, Rocket, ShieldCheck, Workflow } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import {
  listAssurancePacks,
  publishAssurancePack,
  validateAssurancePack,
  type AssurancePackJson,
  type AssurancePackResponse,
  type AssurancePackValidateResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import styles from "./workflows.module.css";

const STARTER_PACK: AssurancePackJson = {
  schema_version: "zroky.workflow_assurance_pack.v1",
  workflow_key: "refund_resolution",
  version: "1.0.0",
  intent_schema: {
    type: "object",
    required: ["charge_id", "amount_minor", "currency"],
    properties: {
      charge_id: { type: "string" },
      amount_minor: { type: "integer" },
      currency: { type: "string" },
    },
  },
  object_types: [
    {
      key: "refund",
      schema: { type: "object" },
    },
  ],
  effects: [
    {
      key: "refund_created",
      object_type: "refund",
      predicate: "refund.status == 'posted' && refund.amount_minor == intent.amount_minor && refund.currency == intent.currency && refund.charge_id == intent.charge_id",
    },
  ],
  source_bindings: [
    {
      key: "stripe_refund_read",
      connector_capability: "stripe_refund.read",
      object_type: "refund",
      freshness_seconds: 300,
    },
  ],
  recovery_playbooks: [
    {
      key: "reissue_refund",
      incident_type: "missing_refund",
      steps: [],
    },
  ],
};

type ResultState =
  | { type: "idle"; message: string }
  | { type: "validated"; message: string; data: AssurancePackValidateResponse }
  | { type: "published"; message: string; data: AssurancePackResponse }
  | { type: "error"; message: string };

type WorkflowTone = "ready" | "warning" | "critical" | "neutral";

type PackSummary = {
  effects: unknown[];
  intentFields: string[];
  objectTypes: unknown[];
  recoveryPlaybooks: unknown[];
  sourceBindings: unknown[];
  version: string;
  workflowKey: string;
};

function prettyJson(value: unknown): string {
  return JSON.stringify(value);
}

function parseDraft(value: string): AssurancePackJson {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Draft must be a JSON object.");
  }
  return parsed as AssurancePackJson;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function unknownArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function packSummary(pack: AssurancePackJson): PackSummary {
  const intentSchema = pack.intent_schema && typeof pack.intent_schema === "object" ? pack.intent_schema as Record<string, unknown> : {};
  return {
    effects: unknownArray(pack.effects),
    intentFields: stringArray(intentSchema.required),
    objectTypes: unknownArray(pack.object_types),
    recoveryPlaybooks: unknownArray(pack.recovery_playbooks),
    sourceBindings: unknownArray(pack.source_bindings),
    version: typeof pack.version === "string" ? pack.version : "unversioned",
    workflowKey: typeof pack.workflow_key === "string" ? pack.workflow_key : "missing_workflow_key",
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "Request failed.";
}

function fieldValue(item: unknown, key: string, fallback = "-"): string {
  if (!item || typeof item !== "object") return fallback;
  const value = (item as Record<string, unknown>)[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function statusTone(result: ResultState, draftError: string | null): WorkflowTone {
  if (draftError || result.type === "error") return "critical";
  if (result.type === "published" || result.type === "validated") return "ready";
  return "warning";
}

function StatusBadge({ children, tone }: { children: string; tone: WorkflowTone }) {
  return (
    <span className={styles.statusBadge} data-tone={tone}>
      {tone === "critical" ? <AlertTriangle size={12} aria-hidden="true" /> : <CheckCircle2 size={12} aria-hidden="true" />}
      {children}
    </span>
  );
}

export default function WorkflowsPage() {
  const [packs, setPacks] = useState<AssurancePackResponse[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const [packsLoading, setPacksLoading] = useState(true);
  const [packsError, setPacksError] = useState<string | null>(null);
  const [draft, setDraft] = useState(() => prettyJson(STARTER_PACK));
  const [environment, setEnvironment] = useState("production");
  const [result, setResult] = useState<ResultState>({
    type: "idle",
    message: "No validation has run yet.",
  });
  const [busy, setBusy] = useState<"validate" | "publish" | null>(null);
  const selectedPack = packs.find((pack) => pack.id === selectedPackId) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    setPacksLoading(true);
    setPacksError(null);
    setPacks([]);
    setSelectedPackId(null);
    void listAssurancePacks(environment, controller.signal)
      .then((items) => {
        setPacks(items);
        const first = items[0] ?? null;
        setSelectedPackId(first?.id ?? null);
        setDraft(prettyJson(first?.pack ?? STARTER_PACK));
      })
      .catch((error) => {
        if (!controller.signal.aborted) setPacksError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPacksLoading(false);
      });
    return () => controller.abort();
  }, [environment]);

  function selectWorkflow(pack: AssurancePackResponse) {
    setSelectedPackId(pack.id);
    setDraft(prettyJson(pack.pack));
    setResult({ type: "idle", message: "No validation has run yet." });
  }

  const parsedDraft = useMemo(() => {
    try {
      const pack = parseDraft(draft);
      return { pack, summary: packSummary(pack), error: null as string | null };
    } catch (error) {
      return { pack: null, summary: null, error: errorMessage(error) };
    }
  }, [draft]);

  const tone = selectedPack && result.type === "idle" ? "ready" : statusTone(result, parsedDraft.error);
  const summary = parsedDraft.summary;
  const validationLabel = parsedDraft.error
    ? "Invalid draft"
    : result.type === "published"
      ? "Published"
      : result.type === "validated"
        ? "Validated"
        : selectedPack?.status ?? "Unpublished draft";
  const activePacks = packs.filter((pack) => pack.status === "active").length;
  const needsBinding = packs.filter((pack) => {
    const item = packSummary(pack.pack);
    return item.effects.length === 0 || item.sourceBindings.length === 0;
  }).length;
  const sourceBindings = summary?.sourceBindings ?? [];
  const expectedEffects = summary?.effects ?? [];
  const recoveryPlaybooks = summary?.recoveryPlaybooks ?? [];
  const selectedVersions = packs.filter((pack) => pack.workflow_key === summary?.workflowKey).map((pack) => pack.version);
  const workflowRows = [
    {
      label: "Expected outcome",
      value: fieldValue(expectedEffects[0], "key", "No effect defined"),
      detail: fieldValue(expectedEffects[0], "predicate", "Agent outcome cannot be verified without an expected effect."),
      status: expectedEffects.length > 0 ? "Ready" : "Blocked",
      tone: expectedEffects.length > 0 ? "ready" : "critical",
    },
    {
      label: "Source-of-truth binding",
      value: fieldValue(sourceBindings[0], "key", "No source binding"),
      detail: sourceBindings.length > 0
        ? `${fieldValue(sourceBindings[0], "connector_capability")} / freshness ${fieldValue(sourceBindings[0], "freshness_seconds")}s`
        : "Connectors must provide read-only proof access.",
      status: sourceBindings.length > 0 ? "Ready" : "Blocked",
      tone: sourceBindings.length > 0 ? "ready" : "critical",
    },
    {
      label: "Recovery path",
      value: fieldValue(recoveryPlaybooks[0], "key", "No recovery playbook"),
      detail: recoveryPlaybooks.length > 0 ? fieldValue(recoveryPlaybooks[0], "incident_type") : "Mismatches will require manual handling.",
      status: recoveryPlaybooks.length > 0 ? "Ready" : "Missing",
      tone: recoveryPlaybooks.length > 0 ? "ready" : "warning",
    },
  ] as const satisfies ReadonlyArray<{ detail: string; label: string; status: string; tone: WorkflowTone; value: string }>;
  const statusCards = [
    {
      detail: sourceBindings.length > 0 && expectedEffects.length > 0 ? "Effect and source binding present." : "Binding or effect missing.",
      status: sourceBindings.length > 0 && expectedEffects.length > 0 ? "OK" : "Blocked",
      title: "Publish gate",
      tone: sourceBindings.length > 0 && expectedEffects.length > 0 ? "ready" as WorkflowTone : "critical" as WorkflowTone,
    },
    {
      detail: packsError ?? parsedDraft.error ?? (result.type === "idle" ? "No validation run for this draft." : result.message),
      status: packsError || parsedDraft.error || result.type === "error" ? "Blocked" : "OK",
      title: "Backend response",
      tone: packsError || parsedDraft.error || result.type === "error" ? "critical" as WorkflowTone : "ready" as WorkflowTone,
    },
    {
      detail: sourceBindings.length > 0 && expectedEffects.length > 0 ? "Contract schema and bindings valid." : "Binding or effect missing.",
      status: sourceBindings.length > 0 && expectedEffects.length > 0 ? "Valid" : "Missing",
      title: "Runtime contract",
      tone: sourceBindings.length > 0 && expectedEffects.length > 0 ? "ready" as WorkflowTone : "warning" as WorkflowTone,
    },
  ] as const;

  async function runValidate() {
    setBusy("validate");
    try {
      const pack = parseDraft(draft);
      const response = await validateAssurancePack(pack);
      setResult({
        type: "validated",
        message: `${response.workflow_key}@${response.version} is valid.`,
        data: response,
      });
    } catch (error) {
      setResult({ type: "error", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  }

  async function runPublish() {
    setBusy("publish");
    try {
      const pack = parseDraft(draft);
      await validateAssurancePack(pack);
      const response = await publishAssurancePack(pack, environment);
      setPacks((items) => [response, ...items.filter((item) => item.id !== response.id)]);
      setSelectedPackId(response.id);
      setResult({
        type: "published",
        message: `${response.workflow_key}@${response.version} published to ${response.environment}.`,
        data: response,
      });
    } catch (error) {
      setResult({ type: "error", message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.workflowsDashboard}>
      <div className={styles.pageTitle}>
        <div>
          <h1>Workflows</h1>
          <p>Assurance Packs, policy binding, and trusted workflow contracts</p>
        </div>
      </div>

      <section className={styles.hero} data-tone={tone} aria-label="Workflow posture">
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>Control surface</p>
          <div className={styles.heroTitleLine}>
            <h2>{summary?.workflowKey ?? "Assurance Pack draft"}</h2>
            <StatusBadge tone={tone}>{validationLabel}</StatusBadge>
          </div>
          <p>Expected effects and source bindings used to verify this workflow.</p>
          <code className={styles.denominator}>
            {summary
              ? `${summary.workflowKey} / v${summary.version} / ${summary.effects.length} effects / ${summary.sourceBindings.length} sources / ${environment}`
              : "Draft cannot be parsed yet"}
          </code>
        </div>
        <div className={styles.heroActions}>
          <DashboardButton
            className={styles.blackButton}
            icon={<CheckCircle2 size={15} />}
            loading={busy === "validate"}
            onClick={runValidate}
            variant="soft"
          >
            Validate
          </DashboardButton>
          <DashboardButton
            disabled={Boolean(parsedDraft.error)}
            icon={<Rocket size={15} />}
            loading={busy === "publish"}
            onClick={runPublish}
            variant={result.type === "validated" || result.type === "published" ? "primary" : "soft"}
          >
            Publish
          </DashboardButton>
        </div>
      </section>

      <section className={styles.metricStrip} aria-label="Workflow contract metrics">
        {[
          { label: "Assurance Packs", value: packsLoading ? "-" : String(packs.length), tone: "neutral" as WorkflowTone, icon: Workflow },
          { label: "Active packs", value: String(activePacks), tone: activePacks > 0 ? "ready" as WorkflowTone : "warning" as WorkflowTone, icon: ShieldCheck },
          { label: "Needs binding", value: String(needsBinding), tone: needsBinding > 0 ? "warning" as WorkflowTone : "ready" as WorkflowTone, icon: Database },
          { label: "Intent fields", value: String(summary?.intentFields.length ?? 0), tone: "neutral" as WorkflowTone, icon: FileJson },
          { label: "Versions", value: String(selectedVersions.length), tone: "neutral" as WorkflowTone, icon: GitBranch },
          { label: "Publish state", value: selectedPack?.status ?? (result.type === "published" ? "active" : "draft"), tone, icon: Rocket },
        ].map(({ label, value, tone: itemTone, icon: Icon }) => (
          <article className={styles.metricCell} data-tone={itemTone} key={label}>
            <span>
              <Icon size={15} aria-hidden="true" />
              {label}
            </span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>

      <section className={styles.packManager} aria-label="Assurance Pack manager">
        <div className={cn(styles.card, styles.packListCard)}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Workflow library</h2>
            </div>
          </div>
          <div className={styles.packTable} aria-label="Workflow library">
            <div className={styles.packTableHead}>
              <span>Pack</span>
              <span>Status</span>
              <span>Source</span>
              <span>Environment</span>
              <span>Version</span>
              <span>Action</span>
            </div>
            {packsLoading ? <p className={styles.packEmpty} role="status">Loading published packs...</p> : null}
            {!packsLoading && packs.length === 0 ? <p className={styles.packEmpty}>No Assurance Packs published in {environment}.</p> : null}
            {packs.map((pack) => {
              const item = packSummary(pack.pack);
              const source = fieldValue(item.sourceBindings[0], "connector_capability", "No source binding");
              const selected = pack.id === selectedPackId;
              const itemTone: WorkflowTone = pack.status === "active" ? "ready" : "neutral";
              return (
                <button
                  className={styles.packRow}
                  data-selected={selected ? "true" : undefined}
                  key={pack.id}
                  onClick={() => selectWorkflow(pack)}
                  type="button"
                >
                  <span className={styles.packName}>
                    <strong>{pack.workflow_key}</strong>
                    <small>{item.effects.length} effects / {item.sourceBindings.length} sources</small>
                  </span>
                  <span>
                    <StatusBadge tone={itemTone}>{pack.status}</StatusBadge>
                  </span>
                  <code>{source}</code>
                  <span>{pack.environment}</span>
                  <code>{pack.version}</code>
                  <span className={styles.packAction} aria-hidden="true">...</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className={cn(styles.card, styles.governanceCard)}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Binding summary</h2>
            </div>
          </div>
          <div className={styles.bindingGrid}>
            {[
              ["Source", fieldValue(sourceBindings[0], "connector_capability", "No source binding")],
              ["Environment", selectedPack?.environment ?? environment],
              ["Digest", selectedPack?.pack_digest ?? "Unpublished draft"],
              ["Versions", selectedVersions.join(" -> ") || "Unpublished"],
              ["Status", selectedPack?.status ?? "draft"],
            ].map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className={styles.workspace}>
        <section className={cn(styles.card, styles.contractCard)} aria-labelledby="workflow-contract-title">
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.kicker}>Assurance Pack</p>
              <h2 id="workflow-contract-title">Workflow contract</h2>
              <p>What must be true before Zroky trusts an agent action.</p>
            </div>
            <label className={styles.selectField}>
              <span>Environment</span>
              <select value={environment} onChange={(event) => setEnvironment(event.target.value)}>
                <option value="production">production</option>
                <option value="staging">staging</option>
                <option value="development">development</option>
              </select>
            </label>
          </div>
          <div className={styles.contractTable} role="list">
            {workflowRows.map((row) => (
              <div className={styles.contractRow} key={row.label} role="listitem">
                <span>{row.label}</span>
                <div>
                  <strong data-tone={row.tone}>{row.value}</strong>
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className={styles.sideStack} aria-label="Workflow readiness">
          {statusCards.map((card) => (
            <section className={cn(styles.card, styles.statusCard)} key={card.title}>
              <div>
                <h2>{card.title}</h2>
                <p>{card.detail}</p>
              </div>
              <StatusBadge tone={card.tone}>{card.status}</StatusBadge>
              <ChevronRight size={16} aria-hidden="true" />
            </section>
          ))}
          <pre className={styles.resultPre} aria-label="Workflow API result">
            {result.type === "idle" || result.type === "error" ? result.message : prettyJson(result.data)}
          </pre>
        </aside>
      </div>

      <section className={cn(styles.card, styles.editorCard)} aria-labelledby="workflow-draft-title">
        <div className={styles.panelHeader}>
          <div>
            <p className={styles.kicker}>Advanced</p>
            <h2 id="workflow-draft-title">Pack JSON</h2>
            <p>Edit only when changing the workflow contract source.</p>
          </div>
        </div>
        <textarea
          aria-label="Assurance Pack JSON"
          className={styles.editor}
          rows={1}
          spellCheck={false}
          value={draft}
          wrap="off"
          onChange={(event) => setDraft(event.target.value)}
        />
      </section>
    </div>
  );
}
