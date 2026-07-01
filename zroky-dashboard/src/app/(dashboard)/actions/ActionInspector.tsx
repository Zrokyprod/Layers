"use client";

import { DashboardButtonLink } from "@/components/dashboard-button";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import { StatusPill } from "@/components/status-pill";
import type {
  ActionExecutionAttemptResponse,
  ActionTimelineEventResponse,
} from "@/lib/api";
import type { ActionLifecycleRow } from "@/lib/action-lifecycle";
import { compactJson, formatDateTime, humanize } from "@/lib/format";

type InspectorFact = {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
};

type InspectorJsonSection = {
  title: string;
  value: unknown;
};

type ActionInspectorProps = {
  row: ActionLifecycleRow | null;
  timeline: ActionTimelineEventResponse[];
  attempts: ActionExecutionAttemptResponse[];
};

function valuePresent(value: unknown): boolean {
  if (value == null || value === "") return false;
  if (typeof value === "object" && !Array.isArray(value)) return Object.keys(value).length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function FactGrid({ facts }: { facts: InspectorFact[] }) {
  const shown = facts.filter((fact) => fact.value != null && fact.value !== "");
  if (shown.length === 0) return null;
  return (
    <dl className="al-fact-grid">
      {shown.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.mono ? <code>{fact.value}</code> : fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function JsonSections({ sections }: { sections: InspectorJsonSection[] }) {
  const shown = sections.filter((section) => valuePresent(section.value));
  if (shown.length === 0) return null;
  return (
    <div className="al-detail-grid">
      {shown.map((section) => (
        <details key={section.title} className="al-json-section">
          <summary>
            <h4>{section.title}</h4>
            <span>JSON</span>
          </summary>
          <pre>{compactJson(section.value)}</pre>
        </details>
      ))}
    </div>
  );
}

function TimelineList({ timeline }: { timeline: ActionTimelineEventResponse[] }) {
  return (
    <section>
      <h4>Action timeline</h4>
      {timeline.length === 0 ? (
        <p>No timeline events yet.</p>
      ) : (
        <ol>
          {timeline.slice(0, 8).map((event) => (
            <li key={event.event_id}>
              <strong>{humanize(event.event_type)}</strong>
              <span>{formatDateTime(event.created_at)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function AttemptList({ attempts, fallback }: { attempts: ActionExecutionAttemptResponse[]; fallback: ActionExecutionAttemptResponse | null }) {
  const shown = attempts.length > 0 ? attempts : fallback ? [fallback] : [];
  return (
    <section>
      <h4>Execution attempts</h4>
      {shown.length === 0 ? (
        <p>No execution attempts yet.</p>
      ) : (
        <ol>
          {shown.slice(0, 6).map((attempt) => (
            <li key={attempt.attempt_id}>
              <strong>{humanize(attempt.status)}</strong>
              <span>{attempt.runner_id}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function ActionInspector({ attempts, row, timeline }: ActionInspectorProps) {
  if (!row) {
    return (
      <section className="al-empty-state al-inspector-empty" aria-label="Selected action lifecycle">
        <h2>No action selected</h2>
        <p>Select a protected action to inspect policy, runner execution, verification, and receipt state.</p>
      </section>
    );
  }

  const facts: InspectorFact[] = [
    { label: "Stage", value: row.stage.label },
    { label: "Action ID", value: row.actionId, mono: true },
    { label: "Decision", value: row.decisionId, mono: true },
    { label: "Digest", value: row.digest, mono: true },
    { label: "System", value: row.systemRef, mono: true },
    { label: "Environment", value: row.environment ?? undefined },
    { label: "Operation", value: row.operationKind ? humanize(row.operationKind) : null },
    { label: "Attempt", value: row.attemptId, mono: true },
    { label: "Outcome", value: row.outcomeId, mono: true },
  ];
  const sections: InspectorJsonSection[] = [
    { title: "Intent", value: row.intent?.canonical_intent },
    { title: "Policy decision", value: row.decision?.intended_action ?? row.decision?.policy_hit },
    { title: "Runner execution", value: row.attempt?.execution_plan ?? row.attempt?.result_summary },
    { title: "Verification", value: row.outcome ? { claimed: row.outcome.claimed, actual: row.outcome.actual, comparison: row.outcome.comparison } : null },
  ];

  return (
    <section className="al-inspector-panel" aria-label="Selected action lifecycle">
      <header className="al-inspector-header">
        <div>
          <span className="al-eyebrow">Selected action</span>
          <h2>{row.title}</h2>
          <p>
            {row.agentName} / {row.actionType}
          </p>
        </div>
        <StatusPill value={row.status} label={row.statusLabel} tone={row.statusTone} />
      </header>

      <div className={`al-stage-summary al-tone-${row.stage.tone}`}>
        <div>
          <span className="al-eyebrow">Lifecycle stage</span>
          <strong>{row.stage.label}</strong>
          <p>{row.stage.detail}</p>
        </div>
        <div className="al-status-stack">
          <StatusPill value={row.proofStatus} label={row.proofLabel} tone={row.proofTone} />
          <StatusPill value={row.receiptStatus} label={row.receiptLabel} tone={row.receiptTone} />
        </div>
      </div>

      <ProofChainStepper steps={row.proofChain} variant="compact" />
      <FactGrid facts={facts} />

      <div className="al-link-row">
        {row.decisionId ? (
          <DashboardButtonLink href={row.hrefs.approvals ?? "/approvals"} variant="soft">
            Open Approvals
          </DashboardButtonLink>
        ) : null}
        <DashboardButtonLink href={row.hrefs.outcomes ?? "/outcomes"} variant="soft">
          Open Outcomes
        </DashboardButtonLink>
        <DashboardButtonLink href={row.hrefs.evidence ?? "/evidence"} variant="primary">
          {row.kind === "orphan_decision" ? "Open Evidence Pack" : "Open Action Receipt"}
        </DashboardButtonLink>
      </div>

      <JsonSections sections={sections} />

      {row.kind === "action_intent" ? (
        <div className="al-operational-grid">
          <TimelineList timeline={timeline} />
          <AttemptList attempts={attempts} fallback={row.attempt} />
        </div>
      ) : null}
    </section>
  );
}
