"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, FileJson, Rocket, ShieldCheck } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  DashboardWorkspace,
  type DashboardMetric,
} from "@/components/dashboard-scaffold";
import { StatusPill } from "@/components/status-pill";
import {
  publishAssurancePack,
  validateAssurancePack,
  type AssurancePackJson,
  type AssurancePackResponse,
  type AssurancePackValidateResponse,
} from "@/lib/api";

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

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "Request failed.";
}

export default function WorkflowsPage() {
  const [draft, setDraft] = useState(() => prettyJson(STARTER_PACK));
  const [environment, setEnvironment] = useState("production");
  const [result, setResult] = useState<ResultState>({
    type: "idle",
    message: "No validation has run yet.",
  });
  const [busy, setBusy] = useState<"validate" | "publish" | null>(null);

  const metrics = useMemo<DashboardMetric[]>(
    () => [
      {
        id: "draft",
        label: "Draft",
        value: "JSON",
        helper: "Workflow Assurance Pack source of truth.",
        tone: "setup",
      },
      {
        id: "validate",
        label: "Validate",
        value: result.type === "validated" || result.type === "published" ? "Passed" : "Required",
        helper: "Backend schema check before publish.",
        tone: result.type === "error" ? "danger" : result.type === "idle" ? "warning" : "success",
      },
      {
        id: "publish",
        label: "Publish",
        value: result.type === "published" ? result.data.status : environment,
        helper: "Immutable pack stored by workflow key and version.",
        tone: result.type === "published" ? "success" : "setup",
      },
    ],
    [environment, result],
  );

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
    <main className="policies-page workflows-page">
      <DashboardVerdictHero
        eyebrow="Workflow Builder"
        title="Ship governed agent workflows from an Assurance Pack."
        copy="Draft the workflow contract, validate it against the backend schema, then publish the immutable version agents will use at runtime."
        tone={result.type === "error" ? "danger" : result.type === "published" ? "success" : "setup"}
        icon={<ShieldCheck size={22} />}
        pill={result.type === "published" ? "Published" : "Draft mode"}
        actions={
          <>
            <DashboardButton
              icon={<CheckCircle2 size={16} />}
              loading={busy === "validate"}
              onClick={runValidate}
              variant="soft"
            >
              Validate
            </DashboardButton>
            <DashboardButton
              icon={<Rocket size={16} />}
              loading={busy === "publish"}
              onClick={runPublish}
              variant="primary"
            >
              Publish
            </DashboardButton>
          </>
        }
      />

      <DashboardMetricStrip ariaLabel="Workflow builder status" columns={3} metrics={metrics} />

      <DashboardWorkspace
        left={
          <section className="agent-setup-card" aria-labelledby="workflow-draft-title">
            <div>
              <span className="dashboard-eyebrow">Pack draft</span>
              <h2 id="workflow-draft-title">Workflow Assurance Pack JSON</h2>
              <p>Edit the contract and validate before publish. Invalid JSON is blocked locally.</p>
            </div>
            <label className="agent-setup-field">
              <span>Environment</span>
              <select value={environment} onChange={(event) => setEnvironment(event.target.value)}>
                <option value="production">production</option>
                <option value="staging">staging</option>
                <option value="development">development</option>
              </select>
            </label>
            <label className="agent-setup-field">
              <span>Assurance Pack</span>
              <textarea
                aria-label="Assurance Pack JSON"
                spellCheck={false}
                rows={28}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
          </section>
        }
        right={
          <aside className="agent-setup-card" aria-labelledby="workflow-result-title">
            <div>
              <span className="dashboard-eyebrow">Result</span>
              <h2 id="workflow-result-title">Validation and publish status</h2>
            </div>
            <StatusPill
              value={result.type}
              tone={result.type === "error" ? "danger" : result.type === "idle" ? "warning" : "success"}
            />
            <p>{result.message}</p>
            <pre aria-label="Workflow API result">
              {result.type === "idle" || result.type === "error" ? result.message : prettyJson(result.data)}
            </pre>
            <div>
              <span className="dashboard-eyebrow">Runtime contract</span>
              <ul>
                <li>Governance happens before execution.</li>
                <li>Workflow key and version are immutable.</li>
                <li>Published pack becomes the verification source for agents.</li>
              </ul>
            </div>
            <FileJson size={20} aria-hidden="true" />
          </aside>
        }
      />
    </main>
  );
}
