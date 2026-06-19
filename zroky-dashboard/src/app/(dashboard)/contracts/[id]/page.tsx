"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  FileLock2,
  GitCommitHorizontal,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import {
  getRegressionContract,
  type RegressionContractView,
  type RegressionContractVersionView,
} from "@/lib/api";

type ProofCheck = {
  label: string;
  value: string;
  ok: boolean;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function activeVersion(contract: RegressionContractView): RegressionContractVersionView | null {
  return contract.versions.find((version) => version.id === contract.active_version_id) ?? contract.versions[0] ?? null;
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringValue(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "Unavailable";
}

function proofChecks(
  contract: RegressionContractView,
  version: RegressionContractVersionView | null,
): ProofCheck[] {
  if (!version) {
    return [];
  }
  const proof = asRecord(version.spec_json.proof);
  const trialPolicy = asRecord(version.trial_policy);
  const requiredTrials = Math.max(10, numberValue(trialPolicy.required_trials, 10));
  const criticalTolerance = numberValue(trialPolicy.critical_violation_tolerance, 0);
  const completedTrials = numberValue(proof.required_trials);
  const criticalViolations = numberValue(proof.critical_violations);
  const ciGateVerdict = stringValue(proof.ci_gate_verdict);
  const incidentConfirmed = proof.incident_confirmed === true;

  return [
    {
      label: "Original incident",
      value: incidentConfirmed ? "Confirmed" : "Missing confirmation",
      ok: incidentConfirmed,
    },
    {
      label: "Baseline reproduction",
      value: proof.baseline_reproduced === true ? "Failed as expected" : "Not reproduced",
      ok: proof.baseline_reproduced === true,
    },
    {
      label: "Candidate SHA",
      value: stringValue(proof.candidate_sha),
      ok: typeof proof.candidate_sha === "string" && proof.candidate_sha.trim().length > 0,
    },
    {
      label: "Candidate trials",
      value: `${completedTrials}/${requiredTrials} passed`,
      ok: completedTrials >= requiredTrials && proof.candidate_verified === true,
    },
    {
      label: "Critical violations",
      value: String(criticalViolations),
      ok: criticalViolations <= criticalTolerance,
    },
    {
      label: "Fixture",
      value: version.fixture_set_id && proof.fixture_pinned === true ? "Pinned" : "Not pinned",
      ok: Boolean(version.fixture_set_id && proof.fixture_pinned === true),
    },
    {
      label: "Evaluator bundle",
      value: proof.evaluator_bundle_pinned === true ? version.evaluator_bundle_version : "Not pinned",
      ok: proof.evaluator_bundle_pinned === true,
    },
    {
      label: "Admin approval",
      value: version.approved_at ? `Approved ${formatDate(version.approved_at)}` : "Not approved",
      ok: Boolean(version.approved_at),
    },
    {
      label: "CI gate verdict",
      value: ciGateVerdict === "Unavailable" && contract.status === "active" ? "Active gate" : ciGateVerdict,
      ok: ciGateVerdict === "pass" || contract.status === "active",
    },
  ];
}

function ProofStatus({ check }: { check: ProofCheck }) {
  return (
    <div className={`gm-kpi-card ${check.ok ? "is-active" : ""}`}>
      <span>{check.label}</span>
      <strong>{check.value}</strong>
      <small>{check.ok ? "Proof satisfied" : "Blocks activation"}</small>
    </div>
  );
}

export default function ContractProofPage() {
  const params = useParams<{ id?: string }>();
  const contractId = typeof params?.id === "string" ? params.id : "";
  const contractQuery = useQuery({
    queryKey: ["regression-contract", contractId],
    queryFn: ({ signal }) => getRegressionContract(contractId, signal),
    enabled: Boolean(contractId),
  });

  if (contractQuery.isLoading) {
    return (
      <div className="goldens-mvp">
        <div className="gm-empty">
          <ShieldCheck aria-hidden="true" />
          <strong>Loading contract proof</strong>
          <span>Checking pinned fixture, baseline, candidate, and gate evidence.</span>
        </div>
      </div>
    );
  }

  if (contractQuery.error || !contractQuery.data) {
    return (
      <div className="goldens-mvp">
        <div className="gm-notice">
          <AlertTriangle aria-hidden="true" />
          <strong>Contract proof unavailable.</strong>
          <span>{contractQuery.error?.message ?? "Contract was not found."}</span>
        </div>
      </div>
    );
  }

  const contract = contractQuery.data;
  const version = activeVersion(contract);
  const checks = proofChecks(contract, version);
  const passedChecks = checks.filter((check) => check.ok).length;
  const ready = checks.length > 0 && passedChecks === checks.length;

  return (
    <div className="goldens-mvp">
      <section className="gm-hero">
        <div>
          <div className="gm-eyebrow">
            <FileLock2 aria-hidden="true" />
            Contract proof
          </div>
          <h1>{contract.name}</h1>
          <p>
            Customer-facing proof that the original incident was reproduced, the candidate SHA passed,
            and the active CI gate is tied to pinned evidence.
          </p>
        </div>
        <div className="gm-hero-actions">
          <Link className="btn btn-soft" href="/contracts">Back to Contracts</Link>
          {version?.fixture_set_id ? (
            <Link className="btn btn-primary" href={`/goldens/${version.fixture_set_id}`}>Open fixture</Link>
          ) : null}
        </div>
      </section>

      <section className="gm-kpi-grid" aria-label="Contract proof summary">
        <div className={`gm-kpi-card ${ready ? "is-active" : ""}`}>
          <span>Proof status</span>
          <strong>{ready ? "Launch ready" : "Incomplete"}</strong>
          <small>{passedChecks}/{checks.length || 9} proof checks satisfied</small>
        </div>
        <div className="gm-kpi-card">
          <span>Contract version</span>
          <strong>{version ? `v${version.version_number}` : "None"}</strong>
          <small>{version ? version.id : "No immutable version created"}</small>
        </div>
        <div className="gm-kpi-card">
          <span>Status</span>
          <strong>{contract.status}</strong>
          <small>{contract.active_version_id ? "Active version pinned" : "No active version"}</small>
        </div>
      </section>

      {!ready ? (
        <div className="gm-notice">
          <XCircle aria-hidden="true" />
          <strong>Activation proof is incomplete.</strong>
          <span>Repository replay must produce 10/10 evidence with zero critical violations before this contract can block paid-launch CI.</span>
        </div>
      ) : (
        <div className="gm-notice-muted">
          <CheckCircle2 aria-hidden="true" />
          <strong>Contract proof is complete.</strong>
          <span>This version is backed by pinned fixture, evaluator, baseline, candidate SHA, and admin approval.</span>
        </div>
      )}

      <section className="gm-kpi-grid" aria-label="Proof checks">
        {checks.map((check) => (
          <ProofStatus key={check.label} check={check} />
        ))}
      </section>

      <section className="gm-table-section">
        <header className="gm-section-header">
          <div>
            <h2>Immutable Version Evidence</h2>
            <p>These pins are the trust boundary for repository replay and CI gates.</p>
          </div>
        </header>
        <div className="gm-table-wrap">
          <table className="gm-table">
            <tbody>
              <tr>
                <th>Source incident</th>
                <td>{contract.source_issue_id || "Unavailable"}</td>
              </tr>
              <tr>
                <th>Baseline release</th>
                <td>{version?.baseline_release_id || "Unavailable"}</td>
              </tr>
              <tr>
                <th>Fixture set</th>
                <td>{version?.fixture_set_id || "Unavailable"}</td>
              </tr>
              <tr>
                <th>Evaluator bundle</th>
                <td>{version?.evaluator_bundle_version || "Unavailable"}</td>
              </tr>
              <tr>
                <th>Created</th>
                <td>{formatDate(version?.created_at)}</td>
              </tr>
              <tr>
                <th>Approved by</th>
                <td>{version?.approved_by || "Unavailable"}</td>
              </tr>
              <tr>
                <th>Candidate</th>
                <td>
                  <span className="gm-inline-icon">
                    <GitCommitHorizontal aria-hidden="true" />
                    {stringValue(asRecord(version?.spec_json.proof).candidate_sha)}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
