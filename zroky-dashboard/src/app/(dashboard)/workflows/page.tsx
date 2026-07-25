"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, FileJson, GitBranch, Rocket, ShieldCheck, Workflow } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import {
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
    required: ["customer_id", "amount_usd"],
    properties: {
      customer_id: { type: "string" },
      amount_usd: { type: "number" },
    },
  },
  object_types: [
    {
      name: "refund",
      schema: {
        required: ["id", "customer_id", "amount_usd", "status"],
      },
    },
  ],
  effects: [
    {
      name: "refund_created",
      object_type: "refund",
      cardinality: "exactly_one",
      predicate: "refund.customer_id == intent.customer_id && refund.amount_usd == intent.amount_usd",
    },
  ],
  source_bindings: [
    {
      name: "ledger_refunds",
      connector: "ledger",
      object_type: "refund",
      freshness_seconds: 300,
    },
  ],
  recovery_playbooks: [
    {
      name: "manual_refund_review",
      trigger: "missing_or_conflicting_refund",
      steps: ["Hold downstream communication", "Open finance review ticket", "Attach evidence bundle"],
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
  return JSON.stringify(value, null, 2);
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

function fieldValue(item: unknown, key: string, fallback = "—"): string {
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

function Sparkline({ tone }: { tone: WorkflowTone }) {
  return (
    <svg className={styles.sparkline} viewBox="0 0 96 22" aria-hidden="true" data-tone={tone}>
      <polyline points="3,16 20,13 37,15 54,8 72,10 93,5" />
    </svg>
  );
}

export default function WorkflowsPage() {
  const [draft, setDraft] = useState(() => prettyJson(STARTER_PACK));
  const [environment, setEnvironment] = useState("production");
  const [result, setResult] = useState<ResultState>({
    type: "idle",
    message: "No validation has run yet.",
  });
  const [busy, setBusy] = useState<"validate" | "publish" | null>(null);

  const parsedDraft = useMemo(() => {
    try {
      const pack = parseDraft(draft);
      return { pack, summary: packSummary(pack), error: null as string | null };
    } catch (error) {
      return { pack: null, summary: null, error: errorMessage(error) };
    }
  }, [draft]);

  const tone = statusTone(result, parsedDraft.error);
  const summary = parsedDraft.summary;
  const validationLabel = parsedDraft.error ? "Invalid draft" : result.type === "published" ? "Published" : result.type === "validated" ? "Validated" : "Needs validation";
  const sourceBindings = summary?.sourceBindings ?? [];
  const expectedEffects = summary?.effects ?? [];
  const recoveryPlaybooks = summary?.recoveryPlaybooks ?? [];
  const workflowRows = [
    {
      label: "Expected outcome",
      value: fieldValue(expectedEffects[0], "name", "No effect defined"),
      detail: fieldValue(expectedEffects[0], "predicate", "Agent outcome cannot be verified without an expected effect."),
      status: expectedEffects.length > 0 ? "Ready" : "Blocked",
      tone: expectedEffects.length > 0 ? "ready" : "critical",
    },
    {
      label: "Source-of-truth binding",
      value: fieldValue(sourceBindings[0], "name", "No source binding"),
      detail: sourceBindings.length > 0
        ? `${fieldValue(sourceBindings[0], "connector")} · freshness ${fieldValue(sourceBindings[0], "freshness_seconds")}s`
        : "Connectors must provide read-only proof access.",
      status: sourceBindings.length > 0 ? "Ready" : "Blocked",
      tone: sourceBindings.length > 0 ? "ready" : "critical",
    },
    {
      label: "Policy guardrails",
      value: "Bound at policy check",
      detail: "Approval and deny rules are evaluated before execution.",
      status: "Linked",
      tone: "neutral",
    },
    {
      label: "SLA / owner",
      value: "Not defined in pack",
      detail: "Add only when Operations needs real SLA breach math.",
      status: "Missing",
      tone: "warning",
    },
    {
      label: "Recovery path",
      value: fieldValue(recoveryPlaybooks[0], "name", "No recovery playbook"),
      detail: recoveryPlaybooks.length > 0 ? fieldValue(recoveryPlaybooks[0], "trigger") : "Mismatches will require manual handling.",
      status: recoveryPlaybooks.length > 0 ? "Ready" : "Missing",
      tone: recoveryPlaybooks.length > 0 ? "ready" : "warning",
    },
  ] as const satisfies ReadonlyArray<{ detail: string; label: string; status: string; tone: WorkflowTone; value: string }>;
  const readinessRows = [
    {
      label: "Draft JSON",
      detail: parsedDraft.error ?? "Parseable Assurance Pack object",
      status: parsedDraft.error ? "Blocked" : "Ready",
      tone: parsedDraft.error ? "critical" : "ready",
    },
    {
      label: "Backend schema",
      detail: result.type === "validated" || result.type === "published" ? `${summary?.workflowKey}@${summary?.version} accepted` : "Validate before publish",
      status: result.type === "error" ? "Blocked" : result.type === "idle" ? "Pending" : "Ready",
      tone: result.type === "error" ? "critical" : result.type === "idle" ? "warning" : "ready",
    },
    {
      label: "Source bindings",
      detail: `${summary?.sourceBindings.length ?? 0} source-of-truth read path${summary?.sourceBindings.length === 1 ? "" : "s"}`,
      status: (summary?.sourceBindings.length ?? 0) > 0 ? "Ready" : "Missing",
      tone: (summary?.sourceBindings.length ?? 0) > 0 ? "ready" : "warning",
    },
    {
      label: "Expected effects",
      detail: `${summary?.effects.length ?? 0} outcome rule${summary?.effects.length === 1 ? "" : "s"} defined`,
      status: (summary?.effects.length ?? 0) > 0 ? "Ready" : "Missing",
      tone: (summary?.effects.length ?? 0) > 0 ? "ready" : "warning",
    },
    {
      label: "Recovery playbook",
      detail: `${summary?.recoveryPlaybooks.length ?? 0} recovery path${summary?.recoveryPlaybooks.length === 1 ? "" : "s"}`,
      status: (summary?.recoveryPlaybooks.length ?? 0) > 0 ? "Ready" : "Missing",
      tone: (summary?.recoveryPlaybooks.length ?? 0) > 0 ? "ready" : "warning",
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
    <main className={styles.workflowsDashboard} aria-label="ZROKY Workflows dashboard">
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
          <p>
            Define what “correct” means before agents run. ZROKY uses this pack to govern intent,
            verify source-of-truth outcomes, trigger recovery, and produce signed evidence.
          </p>
          <code className={styles.denominator}>
            {summary
              ? `${summary.workflowKey} · v${summary.version} · ${summary.effects.length} effects · ${summary.sourceBindings.length} sources · ${environment}`
              : "Draft cannot be parsed yet"}
          </code>
        </div>
        <div className={styles.heroActions}>
          <DashboardButton
            icon={<CheckCircle2 size={15} />}
            loading={busy === "validate"}
            onClick={runValidate}
            variant={result.type === "validated" || result.type === "published" ? "soft" : "primary"}
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
          { label: "Expected effects", value: String(summary?.effects.length ?? 0), tone: "ready" as WorkflowTone, icon: ShieldCheck },
          { label: "Source bindings", value: String(summary?.sourceBindings.length ?? 0), tone: "ready" as WorkflowTone, icon: Database },
          { label: "Intent fields", value: String(summary?.intentFields.length ?? 0), tone: "neutral" as WorkflowTone, icon: FileJson },
          { label: "Object types", value: String(summary?.objectTypes.length ?? 0), tone: "neutral" as WorkflowTone, icon: GitBranch },
          { label: "Recovery paths", value: String(summary?.recoveryPlaybooks.length ?? 0), tone: "warning" as WorkflowTone, icon: Workflow },
          { label: "Publish state", value: result.type === "published" ? "active" : "draft", tone, icon: Rocket },
        ].map(({ label, value, tone: itemTone, icon: Icon }) => (
          <article className={styles.metricCell} data-tone={itemTone} key={label}>
            <span>
              <Icon size={15} aria-hidden="true" />
              {label}
            </span>
            <strong>{value}</strong>
            <Sparkline tone={itemTone} />
          </article>
        ))}
      </section>

      <div className={styles.workspace}>
        <section className={cn(styles.card, styles.contractCard)} aria-labelledby="workflow-contract-title">
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.kicker}>Assurance Pack</p>
              <h2 id="workflow-contract-title">Workflow contract</h2>
              <p>What must be true before ZROKY trusts an agent action.</p>
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
                <div>
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                  <small>{row.detail}</small>
                </div>
                <StatusBadge tone={row.tone}>{row.status}</StatusBadge>
              </div>
            ))}
          </div>
        </section>

        <aside className={styles.sideStack} aria-label="Workflow readiness">
          <section className={styles.card}>
            <div className={styles.panelHeader}>
              <div>
                <p className={styles.kicker}>Verification readiness</p>
                <h2>Publish gate</h2>
              </div>
            </div>
            <div className={styles.readinessList}>
              {readinessRows.map((row) => (
                <div className={styles.readinessRow} key={row.label}>
                  <div>
                    <strong>{row.label}</strong>
                    <small>{row.detail}</small>
                  </div>
                  <StatusBadge tone={row.tone}>{row.status}</StatusBadge>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.panelHeader}>
              <div>
                <p className={styles.kicker}>Result</p>
                <h2>Backend response</h2>
              </div>
              <StatusBadge tone={tone}>{result.type}</StatusBadge>
            </div>
            {result.type !== "idle" ? <p className={styles.resultMessage}>{result.message}</p> : null}
            <pre className={styles.resultPre} aria-label="Workflow API result">
              {result.type === "idle" || result.type === "error" ? result.message : prettyJson(result.data)}
            </pre>
          </section>

          <section className={styles.card}>
            <div className={styles.panelHeader}>
              <div>
                <p className={styles.kicker}>Runtime contract</p>
                <h2>What this controls</h2>
              </div>
            </div>
            <ul className={styles.contractList}>
              <li>Governance happens before execution.</li>
              <li>Source bindings define proof reads after execution.</li>
              <li>Recovery playbooks handle mismatched or missing outcomes.</li>
              <li>Published workflow key and version are immutable.</li>
            </ul>
          </section>
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
          spellCheck={false}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </section>
    </main>
  );
}
