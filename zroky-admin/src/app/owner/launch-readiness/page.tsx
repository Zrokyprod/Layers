"use client";

import {
  CheckCircle2,
  CircleSlash,
  RefreshCw,
  ShieldAlert,
  TerminalSquare,
} from "lucide-react";

import { useOwnerLaunchReadiness } from "@/lib/hooks";
import type {
  OwnerLaunchGateEvidence,
  OwnerLaunchReadinessGate,
} from "@/lib/owner-api";

function toneForStatus(status: string): "ok" | "warn" | "danger" | "neutral" {
  if (status === "pass") return "ok";
  if (status === "fail" || status === "blocked") return "danger";
  if (status === "not_verified") return "warn";
  return "neutral";
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function formatValue(value: OwnerLaunchGateEvidence["value"]): string {
  if (value === null || value === undefined) return "missing";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return value.toLocaleString();
  return value;
}

function StatusBadge({ status }: { status: string }) {
  const tone = toneForStatus(status);
  return (
    <span className={`owner-money-badge owner-money-badge-${tone}`}>
      {statusLabel(status)}
    </span>
  );
}

function GateIcon({ status }: { status: string }) {
  if (status === "pass") return <CheckCircle2 size={18} aria-hidden="true" />;
  if (status === "fail") return <CircleSlash size={18} aria-hidden="true" />;
  return <ShieldAlert size={18} aria-hidden="true" />;
}

function EvidenceList({ items }: { items: OwnerLaunchGateEvidence[] }) {
  return (
    <div className="owner-money-proof-grid">
      {items.map((item) => (
        <div key={item.label} className="owner-money-proof-item">
          <span>{item.label.replaceAll("_", " ")}</span>
          <code>{formatValue(item.value)}</code>
          {item.detail ? <small>{item.detail}</small> : null}
        </div>
      ))}
    </div>
  );
}

function GateCard({ gate }: { gate: OwnerLaunchReadinessGate }) {
  const tone = toneForStatus(gate.status);
  return (
    <section className={`panel owner-launch-gate owner-launch-gate-${tone}`}>
      <div className="panel-header">
        <div className="owner-launch-gate-title">
          <span className="owner-launch-gate-icon">
            <GateIcon status={gate.status} />
          </span>
          <div>
            <h3>{gate.title}</h3>
            <p>{gate.summary}</p>
          </div>
        </div>
        <StatusBadge status={gate.status} />
      </div>
      <div className="owner-launch-gate-body">
        {gate.blockers.length > 0 ? (
          <div className="owner-launch-blockers">
            <span className="owner-section-label">Blocking Evidence</span>
            <div className="owner-money-proof-stack">
              {gate.blockers.map((blocker) => (
                <span key={blocker} className="owner-money-table-danger">
                  {blocker}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="hint">No blockers reported for this gate.</p>
        )}
        <EvidenceList items={gate.evidence} />
      </div>
    </section>
  );
}

export default function OwnerLaunchReadinessPage() {
  const readinessQuery = useOwnerLaunchReadiness();
  const readiness = readinessQuery.data;

  if (readinessQuery.error) {
    return (
      <div className="owner-page owner-money-page">
        <div className="owner-error">
          {(readinessQuery.error as Error).message}
        </div>
      </div>
    );
  }

  if (!readiness) {
    return (
      <div className="owner-page owner-money-page">
        <section className="panel">
          <div className="panel-header">
            <h3>Final Paid Launch Gate</h3>
          </div>
          <div className="owner-money-proof-body">
            <p className="hint">Loading launch readiness evidence...</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="owner-page owner-money-page">
      <div className="owner-page-header">
        <div>
          <p className="owner-section-label">Final Paid Launch Gate</p>
          <h2>Launch Readiness</h2>
          <p className="hint">{readiness.product_standard}</p>
        </div>
        <button className="btn btn-soft" onClick={() => readinessQuery.refetch()}>
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>

      <section className={`panel owner-launch-hero owner-launch-hero-${toneForStatus(readiness.overall_status)}`}>
        <div className="owner-launch-hero-main">
          <span className="owner-launch-hero-icon">
            <GateIcon status={readiness.paid_launch_allowed ? "pass" : "fail"} />
          </span>
          <div>
            <span className="owner-section-label">Paid Launch Decision</span>
            <h3>{readiness.paid_launch_allowed ? "Paid launch allowed" : "Paid launch blocked"}</h3>
            <p>
              Paid launch is allowed only when every required gate is pass. Current platform
              status is {statusLabel(readiness.overall_status)}.
            </p>
          </div>
        </div>
        <StatusBadge status={readiness.overall_status} />
      </section>

      {readiness.hard_blockers.length > 0 ? (
        <section className="panel owner-launch-blocker-panel">
          <div className="panel-header">
            <h3>Hard Blockers</h3>
            <StatusBadge status="blocked" />
          </div>
          <div className="owner-money-proof-body owner-money-proof-stack">
            {readiness.hard_blockers.map((blocker) => (
              <span key={blocker} className="owner-money-table-danger">
                {blocker}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="owner-launch-grid" aria-label="Required launch gates">
        {readiness.gates.map((gate) => (
          <GateCard key={gate.code} gate={gate} />
        ))}
      </section>

      <section className="panel owner-launch-commands">
        <div className="panel-header">
          <div className="owner-launch-gate-title">
            <span className="owner-launch-gate-icon">
              <TerminalSquare size={18} aria-hidden="true" />
            </span>
            <div>
              <h3>Final Verification Command</h3>
              <p>Run this before marking paid launch ready.</p>
            </div>
          </div>
        </div>
        <div className="owner-launch-command-list">
          {readiness.verification_commands.map((command) => (
            <code key={command}>{command}</code>
          ))}
        </div>
      </section>
    </div>
  );
}
