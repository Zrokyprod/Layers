"use client";

import { useEffect, useState } from "react";
import { Bot, CircleAlert, SearchCheck } from "lucide-react";

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

type InspectorTab = "overview" | "execution" | "developer";

const TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "execution", label: "Execution" },
  { id: "developer", label: "Developer" },
];

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

function VerificationIssueCard({ row }: { row: ActionLifecycleRow }) {
  if (!row.verificationIssue) return null;
  return (
    <section className="al-truth-card al-tone-danger" aria-label="Verification mismatch">
      <div className="al-truth-card-head">
        <div>
          <span className="al-eyebrow">Verification failed because</span>
          <strong>{row.verificationIssue.title}</strong>
          <p>{row.verificationIssue.detail}</p>
        </div>
        <StatusPill value="mismatched" label="Mismatched" tone="danger" />
      </div>
      {row.verificationIssue.fields.length > 0 ? (
        <div className="al-diff-table" role="table" aria-label="Claimed versus actual mismatch">
          <div role="row">
            <span role="columnheader">Field</span>
            <span role="columnheader">Claimed</span>
            <span role="columnheader">Actual</span>
          </div>
          {row.verificationIssue.fields.map((field) => (
            <div role="row" key={field.field}>
              <span role="cell">{field.field}</span>
              <code role="cell">{field.claimed}</code>
              <code role="cell">{field.actual}</code>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function BypassCard({ row }: { row: ActionLifecycleRow }) {
  if (!row.bypassDetail) return null;
  return (
    <section className="al-truth-card al-tone-danger" aria-label="Bypass risk detail">
      <div className="al-truth-card-head">
        <div>
          <span className="al-eyebrow">Bypass risk</span>
          <strong>{row.bypassDetail.title}</strong>
          <p>{row.bypassDetail.detail}</p>
        </div>
        <StatusPill value={row.bypassDetail.classification} label={humanize(row.bypassDetail.classification)} tone="danger" />
      </div>
      <dl className="al-bypass-facts">
        <div>
          <dt>Actor</dt>
          <dd>{row.bypassDetail.actor}</dd>
        </div>
        <div>
          <dt>System</dt>
          <dd>{row.systemRef ?? "-"}</dd>
        </div>
        <div>
          <dt>Mutation</dt>
          <dd>{row.mutation?.mutation_id ?? "-"}</dd>
        </div>
      </dl>
    </section>
  );
}

function OperationalHandoff({ row }: { row: ActionLifecycleRow }) {
  const handoff = row.verificationIssue
    ? {
        eyebrow: "Verification handoff",
        title: "Source-of-record mismatch needs review",
        copy: "Inspect the claimed and actual values before trusting this action outcome.",
        href: row.hrefs.evidence ?? "/evidence",
        label: "Review proof",
        tone: "danger" as const,
        Icon: SearchCheck,
      }
    : ["awaiting_runner", "no_runner", "execution_stalled"].includes(row.stage.id)
      ? {
          eyebrow: "Execution handoff",
          title: row.stage.id === "awaiting_runner" ? "Connect a runner to continue" : row.stage.label,
          copy: row.stage.detail,
          href: "/agents",
          label: "Check runner",
          tone: row.stage.tone,
          Icon: Bot,
        }
      : row.stage.id === "approval"
        ? {
            eyebrow: "Approval handoff",
            title: "Human decision required",
            copy: "This action remains held until an authorized project member decides it.",
            href: row.hrefs.approvals ?? "/approvals",
            label: "Open approval",
            tone: "warning" as const,
            Icon: CircleAlert,
          }
      : row.stage.id === "bypassed"
          ? {
              eyebrow: "Control handoff",
              title: "Investigate the unprotected mutation",
              copy: "Confirm the source actor and decide whether this path must be routed through Zroky.",
              href: row.hrefs.outcomes ?? "/outcomes",
              label: "Investigate bypass",
              tone: "danger" as const,
              Icon: CircleAlert,
            }
          : row.kind === "orphan_decision"
            ? {
                eyebrow: "Partial evidence",
                title: "Guard-only Evidence Pack available",
                copy: "This decision did not use the full Action Intent execution and receipt chain.",
                href: row.hrefs.evidence ?? "/evidence",
                label: "Open Evidence Pack",
                tone: row.stage.tone,
                Icon: SearchCheck,
              }
          : row.stage.id === "blocked"
            ? {
                eyebrow: "Policy result",
                title: "Execution was prevented",
                copy: "Review the policy evidence if this action should be allowed in the future.",
                href: row.hrefs.evidence ?? "/evidence",
                label: "Review evidence",
                tone: "danger" as const,
                Icon: CircleAlert,
              }
            : row.receiptStatus === "generated"
              ? {
                  eyebrow: "Evidence ready",
                  title: "Protected action receipt generated",
                  copy: "Open the receipt to inspect the signed action and verification chain.",
                  href: row.hrefs.evidence ?? "/evidence",
                  label: "Open receipt",
                  tone: "success" as const,
                  Icon: SearchCheck,
                }
              : null;

  if (!handoff && row.agentIdentityKnown) return null;

  return (
    <section className="al-operational" aria-label="Action operational handoff">
      {handoff ? (
        <div className={`al-operational-item al-tone-${handoff.tone}`}>
          <div>
            <span className="al-eyebrow">{handoff.eyebrow}</span>
            <strong>{handoff.title}</strong>
            <p>{handoff.copy}</p>
          </div>
          <DashboardButtonLink href={handoff.href} icon={<handoff.Icon />} variant="primary">
            {handoff.label}
          </DashboardButtonLink>
        </div>
      ) : null}
      {!row.agentIdentityKnown ? (
        <div className="al-operational-item al-tone-danger" role="note">
          <div>
            <span className="al-eyebrow">Runtime identity</span>
            <strong>{row.kind === "bypass_mutation" ? "Source actor was not reported" : "Agent identity was not reported"}</strong>
            <p>Register the runtime identity so future actions can be attributed to the correct agent.</p>
          </div>
          <DashboardButtonLink href="/agents" icon={<Bot />} variant="soft">
            Review agents
          </DashboardButtonLink>
        </div>
      ) : null}
    </section>
  );
}

export function ActionInspector({ attempts, row, timeline }: ActionInspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTab>("overview");

  useEffect(() => {
    setActiveTab("overview");
  }, [row?.id]);

  if (!row) {
    return (
      <section className="al-empty-state al-inspector-empty" aria-label="Selected action lifecycle">
        <h2>No action selected</h2>
        <p>Select a protected action to inspect policy, runner execution, verification, and receipt state.</p>
      </section>
    );
  }

  const operationalFacts: InspectorFact[] = [
    { label: "Environment", value: row.environment ?? undefined },
    { label: "Operation", value: row.operationKind ? humanize(row.operationKind) : null },
    { label: "Source", value: row.sourceLabel },
  ];
  const technicalFacts: InspectorFact[] = [
    { label: "Action ID", value: row.actionId, mono: true },
    { label: "Decision", value: row.decisionId, mono: true },
    { label: "Digest", value: row.digest, mono: true },
    { label: "System", value: row.systemRef, mono: true },
    { label: "Attempt", value: row.attemptId, mono: true },
    { label: "Outcome", value: row.outcomeId, mono: true },
    { label: "Mutation", value: row.mutation?.mutation_id, mono: true },
  ];
  const sections: InspectorJsonSection[] = [
    { title: "Intent", value: row.intent?.canonical_intent },
    { title: "Policy decision", value: row.decision?.intended_action ?? row.decision?.policy_hit },
    { title: "Runner execution", value: row.attempt?.execution_plan ?? row.attempt?.result_summary },
    { title: "Verification", value: row.outcome ? { claimed: row.outcome.claimed, actual: row.outcome.actual, comparison: row.outcome.comparison } : null },
    { title: "Source mutation", value: row.mutation },
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
        <StatusPill value={row.stage.id} label={row.stage.label} tone={row.stage.tone} />
      </header>

      <OperationalHandoff row={row} />

      <section className="al-tabs" aria-label="Action detail tabs">
        <div className="al-tab-list" role="tablist" aria-label="Action details">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`action-tab-${tab.id}`}
              aria-controls={`action-panel-${tab.id}`}
              aria-selected={activeTab === tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`al-tab${activeTab === tab.id ? " is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div
          className="al-tab-panel"
          role="tabpanel"
          id={`action-panel-${activeTab}`}
          aria-labelledby={`action-tab-${activeTab}`}
        >
          {activeTab === "overview" ? (
            <div className="al-tab-stack">
              <BypassCard row={row} />
              <VerificationIssueCard row={row} />
              <ProofChainStepper steps={row.proofChain} variant="compact" />
              <FactGrid facts={operationalFacts} />
            </div>
          ) : null}
          {activeTab === "execution" ? (
            row.kind === "action_intent" ? (
              <div className="al-operational-grid">
                <TimelineList timeline={timeline} />
                <AttemptList attempts={attempts} fallback={row.attempt} />
              </div>
            ) : (
              <div className="al-empty-state">
                <h2>No protected execution</h2>
                <p>This record was not executed through an Action Intent runner.</p>
              </div>
            )
          ) : null}
          {activeTab === "developer" ? (
            <div className="al-tab-stack">
              <FactGrid facts={technicalFacts} />
              <JsonSections sections={sections} />
            </div>
          ) : null}
        </div>
      </section>
    </section>
  );
}
