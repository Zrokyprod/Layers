"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  PlayCircle,
  Radar,
} from "lucide-react";

const modules = [
  {
    key: "agents",
    label: "Agents",
    title: "Agents needing attention",
    icon: Activity,
    metric: "7 live agents",
    insight: "Refund Agent is the top priority because repeated tool retries are lowering success rate and increasing cost.",
    rows: [
      ["Refund Agent", "Critical loop", "43 calls", "Run replay"],
      ["Support Agent", "Healthy", "91% success", "Promote golden"],
      ["Billing Agent", "Drift warning", "$281 risk", "Review drift"],
    ],
  },
  {
    key: "issues",
    label: "Issues",
    title: "Evidence-backed issue queue",
    icon: AlertTriangle,
    metric: "14 grouped traces",
    insight: "Noisy traces are grouped into one owned issue with severity, impact, evidence, and the safest next action.",
    rows: [
      ["Policy fallback", "High", "Stale chunk", "Assign owner"],
      ["Schema mismatch", "Medium", "3 workflows", "Patch parser"],
      ["Weak evidence", "High", "Confident answer", "Run judge"],
    ],
  },
  {
    key: "replay",
    label: "Replay",
    title: "Replay proof lane",
    icon: PlayCircle,
    metric: "3 ready",
    insight: "Candidate fixes are compared against the original incident before the team treats a change as safe.",
    rows: [
      ["Refund loop fix", "Ready", "Original captured", "Compare"],
      ["Tool timeout", "Running", "Sandbox", "Inspect"],
      ["Retrieval patch", "Passed", "Golden ready", "Open PR"],
    ],
  },
  {
    key: "drift",
    label: "Drift",
    title: "Behavior and provider drift",
    icon: Radar,
    metric: "2 watchlists",
    insight: "Provider, judge, latency, and output changes stay tied to the workflows they can break.",
    rows: [
      ["Provider latency", "Watch", "+18% p95", "Measure"],
      ["Judge delta", "Review", "4 prompts", "Calibrate"],
      ["Output length", "Stable", "-2%", "Keep"],
    ],
  },
  {
    key: "cost",
    label: "Cost",
    title: "Cost of failure",
    icon: CircleDollarSign,
    metric: "$1.8k saved",
    insight: "The dashboard separates normal spend from wasted retries, failed loops, and preventable regressions.",
    rows: [
      ["Retry waste", "High", "$281", "Block loop"],
      ["Failed runs", "Medium", "$104", "Fix issue"],
      ["Golden gate", "Saved", "$1.8k", "Keep gate"],
    ],
  },
];

export default function PublicDashboardPreview() {
  const [activeKey, setActiveKey] = useState(modules[0].key);
  const active = useMemo(
    () => modules.find((module) => module.key === activeKey) ?? modules[0],
    [activeKey],
  );
  const ActiveIcon = active.icon;

  return (
    <section id="dashboard" className="public-dashboard-shell" aria-label="Interactive Zroky dashboard preview">
      <div className="public-dashboard-sidebar" aria-label="Dashboard modules">
        <div className="public-dashboard-sidebar-title">
          <span>Workspace</span>
          <strong>Production</strong>
        </div>
        {modules.map((module) => {
          const Icon = module.icon;
          const selected = module.key === active.key;
          return (
            <button
              key={module.key}
              type="button"
              className={selected ? "is-active" : ""}
              onClick={() => setActiveKey(module.key)}
              aria-pressed={selected}
            >
              <Icon aria-hidden="true" />
              <span>{module.label}</span>
            </button>
          );
        })}
      </div>

      <div className="public-dashboard-main">
        <div className="public-dashboard-topbar">
          <div>
            <span>Live command center</span>
            <h2>{active.title}</h2>
          </div>
          <div className="public-dashboard-health" id="status">
            <CheckCircle2 aria-hidden="true" />
            <span>{active.metric}</span>
          </div>
        </div>

        <div className="public-dashboard-grid">
          <div className="public-dashboard-table">
            <div className="public-dashboard-table-head">
              <span>Name</span>
              <span>Status</span>
              <span>Impact</span>
              <span>Action</span>
            </div>
            {active.rows.map((row) => (
              <div key={row.join("-")} className="public-dashboard-row">
                <strong>{row[0]}</strong>
                <span>{row[1]}</span>
                <span>{row[2]}</span>
                <button type="button">{row[3]}</button>
              </div>
            ))}
          </div>

          <aside className="public-insight-panel" aria-live="polite">
            <span className="public-insight-icon">
              <ActiveIcon aria-hidden="true" />
            </span>
            <h3>What to do next</h3>
            <p>{active.insight}</p>
            <div className="public-insight-proof">
              <BarChart3 aria-hidden="true" />
              Evidence, replay state, owner, and release risk stay connected.
            </div>
            <a href="/auth/register" className="public-primary-button">
              Get Started
            </a>
          </aside>
        </div>

        <div className="public-dashboard-strip">
          {[
            ["Capture", "Every prompt, tool call, retrieval chunk, latency, cost, and outcome."],
            ["Diagnose", "One issue with root cause, impact, owner, and evidence."],
            ["Replay", "Compare candidate behavior before shipping."],
            ["Gate", "Promote verified incidents into release checks."],
          ].map(([label, body]) => (
            <div key={label}>
              <strong>{label}</strong>
              <span>{body}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
