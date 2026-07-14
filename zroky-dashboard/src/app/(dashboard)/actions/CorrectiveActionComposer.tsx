"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";
import type {
  ActionContractResponse,
  ActionIntentCreatePayload,
  OutcomeMismatchResponseView,
} from "@/lib/api";
import { humanize } from "@/lib/format";

type JsonSchema = {
  type?: string;
  required?: string[];
  properties?: Record<string, JsonSchema>;
};

type ComposerField = {
  key: string;
  label: string;
  required: boolean;
  section: "resource" | "parameters";
  type: string;
};

export type CorrectionSubmission = {
  idempotencyKey: string;
  payload: ActionIntentCreatePayload;
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function sectionSchema(contract: ActionContractResponse, section: ComposerField["section"]): JsonSchema {
  const root = contract.schema as JsonSchema;
  return root.properties?.[section] ?? {};
}

function contractFields(contract: ActionContractResponse): ComposerField[] {
  return (["resource", "parameters"] as const).flatMap((section) => {
    const schema = sectionSchema(contract, section);
    const required = new Set(schema.required ?? []);
    const keys = [...required];
    if (section === "parameters" && schema.properties?.reason && !required.has("reason")) {
      keys.push("reason");
    }
    return keys.map((key) => ({
      key,
      label: humanize(key),
      required: required.has(key),
      section,
      type: schema.properties?.[key]?.type ?? "string",
    }));
  });
}

function valueText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function initialValues(
  contract: ActionContractResponse,
  responseCase: OutcomeMismatchResponseView,
): Record<string, string> {
  const claimed = record(responseCase.evidence.claimed);
  const actual = record(responseCase.evidence.actual);
  const systemRef = typeof responseCase.evidence.system_ref === "string"
    ? responseCase.evidence.system_ref
    : "";
  const resourceFields = contractFields(contract).filter((field) => field.section === "resource");
  const result: Record<string, string> = {};

  for (const field of contractFields(contract)) {
    let value = claimed[field.key] ?? actual[field.key];
    if (value == null && field.section === "resource" && resourceFields[0]?.key === field.key) {
      value = systemRef;
    }
    if (value == null && field.section === "parameters" && field.key === "reason") {
      value = `Correct outcome mismatch ${responseCase.reconciliation_check_id}`;
    }
    result[`${field.section}:${field.key}`] = valueText(value);
  }
  return result;
}

function parseValue(field: ComposerField, value: string): unknown {
  const trimmed = value.trim();
  if (field.type === "integer") {
    const parsed = Number.parseInt(trimmed, 10);
    if (!Number.isFinite(parsed)) throw new Error(`${field.label} must be a whole number.`);
    return parsed;
  }
  if (field.type === "number") {
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) throw new Error(`${field.label} must be a number.`);
    return parsed;
  }
  if (field.type === "boolean") return trimmed === "true";
  if (field.type === "object" || field.type === "array") {
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      throw new Error(`${field.label} must contain valid JSON.`);
    }
  }
  return trimmed;
}

function correctionIdempotencyKey(caseId: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `outcome-correction:${caseId}:${suffix}`;
}

export function CorrectiveActionComposer({
  busy,
  canCreate,
  contracts,
  error,
  loading,
  onClose,
  onSubmit,
  responseCase,
}: {
  busy: boolean;
  canCreate: boolean;
  contracts: ActionContractResponse[];
  error: string | null;
  loading: boolean;
  onClose: () => void;
  onSubmit: (submission: CorrectionSubmission) => void;
  responseCase: OutcomeMismatchResponseView | null;
}) {
  const originalActionType = typeof responseCase?.evidence.action_type === "string"
    ? responseCase.evidence.action_type
    : null;
  const suggestedContract = contracts.find((item) => item.action_type === originalActionType) ?? null;
  const [contractId, setContractId] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [validationError, setValidationError] = useState<string | null>(null);
  const [idempotencyKey] = useState(() => correctionIdempotencyKey(responseCase?.id ?? "unknown"));

  const effectiveContractId = contractId || suggestedContract?.id || "";
  const contract = contracts.find((item) => item.id === effectiveContractId) ?? null;
  const fields = useMemo(() => contract ? contractFields(contract) : [], [contract]);
  const prefilledValues = useMemo(
    () => contract && responseCase ? initialValues(contract, responseCase) : {},
    [contract, responseCase],
  );

  if (loading) {
    return <section className="corrective-composer" aria-label="Corrective action composer" aria-modal="true" role="dialog">Loading correction context...</section>;
  }

  if (!responseCase) {
    return (
      <section className="corrective-composer" aria-label="Corrective action composer" aria-modal="true" role="dialog">
        <strong>Correction case unavailable</strong>
        <p>The mismatch case may have been removed or belongs to another project.</p>
        <DashboardButton onClick={onClose} size="sm">Close</DashboardButton>
      </section>
    );
  }
  const activeCase = responseCase;

  function submit() {
    if (!contract) {
      setValidationError("Choose the action contract that safely performs this correction.");
      return;
    }
    const resource: Record<string, unknown> = {};
    const parameters: Record<string, unknown> = {};
    try {
      for (const field of fields) {
        const fieldId = `${field.section}:${field.key}`;
        const value = values[fieldId] ?? prefilledValues[fieldId] ?? "";
        if (field.required && !value.trim()) throw new Error(`${field.label} is required by this contract.`);
        if (!value.trim()) continue;
        const target = field.section === "resource" ? resource : parameters;
        target[field.key] = parseValue(field, value);
      }
    } catch (fieldError) {
      setValidationError(fieldError instanceof Error ? fieldError.message : "Review the correction fields.");
      return;
    }
    setValidationError(null);
    onSubmit({
      idempotencyKey,
      payload: {
        contract_version: contract.contract_version,
        action_type: contract.action_type,
        operation_kind: contract.operation_kind,
        environment: "production",
        purpose: {
          kind: "outcome_mismatch_correction",
          mismatch_response_id: activeCase.id,
          reconciliation_check_id: activeCase.reconciliation_check_id,
          original_action_intent_id: activeCase.action_intent_id,
        },
        resource,
        parameters,
        trace_context: {
          source: "outcomes_dashboard",
          mismatch_response_id: activeCase.id,
        },
      },
    });
  }

  return (
    <section className="corrective-composer" aria-label="Corrective action composer" aria-modal="true" role="dialog">
      <div className="corrective-composer-head">
        <div>
          <span className="dashboard-eyebrow">Protected correction</span>
          <h2>Create corrective action</h2>
          <p>Review the target and desired state. Zroky will run policy before any authorization.</p>
        </div>
        <DashboardButton aria-label="Close corrective action composer" icon={<X size={16} />} onClick={onClose} size="icon" variant="ghost" />
      </div>

      <dl className="corrective-context">
        <div><dt>Original action</dt><dd>{humanize(originalActionType, "Unknown action")}</dd></div>
        <div><dt>Source record</dt><dd>{String(responseCase.evidence.system_ref ?? "Not supplied")}</dd></div>
        <div><dt>Case</dt><dd className="mono">{responseCase.id}</dd></div>
      </dl>

      {contracts.length === 0 ? (
        <div className="corrective-empty">
          <strong>No active action contract</strong>
          <p>Install or register a contract before an operator can propose a protected correction.</p>
          <Link href="/agents/setup">Open agent setup</Link>
        </div>
      ) : (
        <div className="corrective-form">
          <label className="corrective-contract-field">
            <span>Correction contract</span>
            <select disabled={!canCreate || busy} value={effectiveContractId} onChange={(event) => {
              setContractId(event.target.value);
              setValues({});
            }}>
              <option value="">Choose the action to perform...</option>
              {contracts.map((item) => (
                <option key={item.id} value={item.id}>
                  {humanize(item.action_type)} · {item.operation_kind} · {item.risk_class}
                </option>
              ))}
            </select>
            <small>{suggestedContract ? "Original action contract suggested; confirm it is the correct remedy." : "Choose deliberately: a correction can differ from the original action."}</small>
          </label>

          {contract ? (
            <div className="corrective-fields">
              {fields.map((field) => (
                <label key={`${field.section}:${field.key}`}>
                  <span>{field.label}{field.required ? " *" : ""}</span>
                  {field.type === "object" || field.type === "array" ? (
                    <textarea
                      disabled={!canCreate || busy}
                      rows={3}
                      value={values[`${field.section}:${field.key}`] ?? prefilledValues[`${field.section}:${field.key}`] ?? ""}
                      onChange={(event) => setValues((current) => ({ ...current, [`${field.section}:${field.key}`]: event.target.value }))}
                    />
                  ) : field.type === "boolean" ? (
                    <select
                      disabled={!canCreate || busy}
                      value={values[`${field.section}:${field.key}`] ?? prefilledValues[`${field.section}:${field.key}`] ?? "false"}
                      onChange={(event) => setValues((current) => ({ ...current, [`${field.section}:${field.key}`]: event.target.value }))}
                    >
                      <option value="false">No</option><option value="true">Yes</option>
                    </select>
                  ) : (
                    <input
                      disabled={!canCreate || busy}
                      inputMode={field.type === "integer" || field.type === "number" ? "decimal" : "text"}
                      value={values[`${field.section}:${field.key}`] ?? prefilledValues[`${field.section}:${field.key}`] ?? ""}
                      onChange={(event) => setValues((current) => ({ ...current, [`${field.section}:${field.key}`]: event.target.value }))}
                    />
                  )}
                  <small>{field.section === "resource" ? "Target record" : "Desired correction"}</small>
                </label>
              ))}
            </div>
          ) : null}

          <div className="corrective-submit-row">
            <p>This creates a new immutable intent. Approval and execution remain on the protected action rail.</p>
            <DashboardButton disabled={!canCreate || !contract || busy} loading={busy} onClick={submit} variant="primary">
              Submit to policy
            </DashboardButton>
          </div>
        </div>
      )}
      {!canCreate ? <p className="corrective-error">Viewer access is read-only. A project member can propose corrections.</p> : null}
      {validationError || error ? <p className="corrective-error" role="alert">{validationError ?? error}</p> : null}
    </section>
  );
}
