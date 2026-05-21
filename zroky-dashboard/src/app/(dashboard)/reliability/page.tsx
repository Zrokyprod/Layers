"use client";

import { useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  DollarSign,
  Loader2,
  RefreshCw,
  Shield,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  useReliabilityLeaderboard,
  useReliabilitySummary,
  useAgentReliabilityHistory,
  useTriggerReliabilityCompute,
} from "@/lib/hooks";
import type { AgentScoreView, ProjectReliabilitySummary } from "@/lib/api";

// ── Health score ring ─────────────────────────────────────────────────────────

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
  const color =
    score >= 80 ? "#22c55e" : score >= 55 ? "#eab308" : "#ef4444";
  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1f2937" strokeWidth={6} />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={6}
        strokeDasharray={`${fill} ${circ - fill}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
        fontSize={size < 48 ? 9 : 12} fontWeight="700" fill={color}
      >
        {Math.round(score)}
      </text>
    </svg>
  );
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return <span className="text-xs text-gray-600">—</span>;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 24;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");
  const last = data[data.length - 1];
  const prev = data[data.length - 2];
  const color = last >= prev ? "#22c55e" : "#ef4444";
  return (
    <svg width={w} height={h} className="shrink-0">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

// ── Determinism bar ───────────────────────────────────────────────────────────

function DetBreakdownBar({ bd }: { bd: AgentScoreView["determinism_breakdown"] }) {
  if (!bd) return <span className="text-xs text-gray-600">—</span>;
  const total = Object.values(bd).reduce((a, b) => a + b, 0);
  if (total === 0) return <span className="text-xs text-gray-600">no data</span>;
  const segments = [
    { key: "deterministic", color: "bg-red-500", label: "Det" },
    { key: "stochastic", color: "bg-yellow-500", label: "Sto" },
    { key: "environmental", color: "bg-blue-500", label: "Env" },
    { key: "unknown", color: "bg-gray-600", label: "Unk" },
  ] as const;
  return (
    <div className="flex items-center gap-1 w-full">
      <div className="flex h-1.5 flex-1 rounded-full overflow-hidden gap-px">
        {segments.map(({ key, color }) =>
          bd[key] > 0 ? (
            <div
              key={key}
              title={`${key}: ${bd[key]}`}
              className={`${color} h-full`}
              style={{ width: `${(bd[key] / total) * 100}%` }}
            />
          ) : null
        )}
      </div>
    </div>
  );
}

// ── Trend badge ───────────────────────────────────────────────────────────────

function TrendBadge({ current, prev }: { current: number; prev: number | null }) {
  if (prev === null) return <span className="text-xs text-gray-600">—</span>;
  const delta = prev - current; // positive = fail rate improved
  if (Math.abs(delta) < 0.005) return <span className="text-xs text-gray-500">flat</span>;
  return delta > 0 ? (
    <span className="flex items-center gap-0.5 text-xs text-green-400">
      <TrendingUp className="w-3 h-3" /> +{(delta * 100).toFixed(1)}%
    </span>
  ) : (
    <span className="flex items-center gap-0.5 text-xs text-red-400">
      <TrendingDown className="w-3 h-3" /> {(delta * 100).toFixed(1)}%
    </span>
  );
}

// ── Agent row ─────────────────────────────────────────────────────────────────

function AgentRow({
  row,
  selected,
  onSelect,
  history,
}: {
  row: AgentScoreView;
  selected: boolean;
  onSelect: () => void;
  history: AgentScoreView[];
}) {
  const sparkData = history.map((h) => h.health_score);
  return (
    <button
      onClick={onSelect}
      className={`w-full flex items-center gap-3 px-4 py-3 border-b border-gray-800/60 text-left hover:bg-gray-800/30 transition-colors ${selected ? "bg-gray-800/50 border-l-2 border-l-indigo-500" : ""}`}
    >
      <ScoreRing score={row.health_score} size={44} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-200 truncate">{row.agent_name}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {(row.fail_rate * 100).toFixed(1)}% fail · {row.call_count.toLocaleString()} calls
        </p>
        <div className="mt-1">
          <DetBreakdownBar bd={row.determinism_breakdown} />
        </div>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <Sparkline data={sparkData} />
        <TrendBadge current={row.fail_rate} prev={row.prev_week_fail_rate} />
      </div>
    </button>
  );
}

// ── Agent detail panel ────────────────────────────────────────────────────────

function AgentPanel({ agentName }: { agentName: string }) {
  const { data: history } = useAgentReliabilityHistory(agentName, 30);
  const latest = history?.[history.length - 1];
  if (!latest) return (
    <div className="flex-1 flex items-center justify-center text-gray-500">
      <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading…
    </div>
  );

  const scoreItems = [
    { label: "Fail Rate Score", value: latest.fail_rate_score, icon: AlertCircle, color: "text-red-400" },
    { label: "Cost Efficiency", value: latest.cost_efficiency_score, icon: DollarSign, color: "text-emerald-400" },
    { label: "Determinism", value: latest.determinism_score, icon: Shield, color: "text-blue-400" },
    { label: "Regression Trend", value: latest.regression_trend_score, icon: Activity, color: "text-indigo-400" },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 border-b border-gray-800 flex items-center gap-4">
        <ScoreRing score={latest.health_score} size={64} />
        <div>
          <h2 className="text-base font-semibold text-white">{agentName}</h2>
          <p className="text-xs text-gray-400">{latest.score_date} · {latest.call_count.toLocaleString()} calls in 7-day window</p>
          {latest.top_failure_axis && (
            <p className="text-xs text-indigo-400 mt-0.5">
              Top failure axis: <span className="font-mono">{latest.top_failure_axis}</span>
            </p>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Score components */}
        <section>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Score Breakdown</h3>
          <div className="grid grid-cols-2 gap-2">
            {scoreItems.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="rounded-lg border border-gray-800 bg-gray-900/40 p-2.5">
                <div className={`flex items-center gap-1.5 mb-1 ${color}`}>
                  <Icon className="w-3.5 h-3.5" />
                  <span className="text-xs font-medium">{label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-gray-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${color.replace("text-", "bg-")}`}
                      style={{ width: `${value}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 tabular-nums">{Math.round(value)}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Determinism breakdown */}
        {latest.determinism_breakdown && (
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Failure Determinism</h3>
            <div className="flex gap-3 flex-wrap">
              {(["deterministic", "stochastic", "environmental", "unknown"] as const).map((cls) => {
                const n = latest.determinism_breakdown![cls];
                if (n === 0) return null;
                const colors: Record<string, string> = {
                  deterministic: "text-red-400 bg-red-950/40 border-red-800/50",
                  stochastic: "text-yellow-400 bg-yellow-950/40 border-yellow-800/50",
                  environmental: "text-blue-400 bg-blue-950/40 border-blue-800/50",
                  unknown: "text-gray-400 bg-gray-800/40 border-gray-700/50",
                };
                return (
                  <span key={cls} className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${colors[cls]}`}>
                    {cls} × {n}
                  </span>
                );
              })}
            </div>
          </section>
        )}

        {/* Metrics */}
        <section className="grid grid-cols-3 gap-2 text-xs text-gray-400">
          <div className="rounded-lg border border-gray-800 p-2">
            <p className="text-gray-500 mb-0.5">Avg Cost</p>
            <p className="text-gray-200 font-mono">${(latest.avg_cost_usd * 100).toFixed(4)}¢</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-2">
            <p className="text-gray-500 mb-0.5">P95 Latency</p>
            <p className="text-gray-200 font-mono">{latest.p95_latency_ms ? `${Math.round(latest.p95_latency_ms)}ms` : "—"}</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-2">
            <p className="text-gray-500 mb-0.5">7-day Fail Rate</p>
            <p className="text-gray-200 font-mono">{(latest.fail_rate * 100).toFixed(2)}%</p>
          </div>
        </section>

        {/* 30-day sparkline full */}
        {history && history.length > 1 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">30-day Health Trend</h3>
            <div className="rounded-lg border border-gray-800 p-3 bg-gray-900/40">
              <Sparkline data={history.map((h) => h.health_score)} />
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>{history[0].score_date}</span>
                <span>{history[history.length - 1].score_date}</span>
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// ── Summary banner ────────────────────────────────────────────────────────────

function SummaryBanner({ s }: { s: ProjectReliabilitySummary }) {
  const color = s.avg_health_score >= 80 ? "text-green-400" : s.avg_health_score >= 55 ? "text-yellow-400" : "text-red-400";
  return (
    <div className="flex items-center gap-6 px-6 py-3 border-b border-gray-800 bg-gray-900/30 text-xs">
      <span className="text-gray-500">{s.agent_count} agents</span>
      <span className={`font-semibold ${color}`}>Avg score: {s.avg_health_score.toFixed(1)}</span>
      {s.best_agent && <span className="text-gray-400">Best: <span className="text-green-400">{s.best_agent}</span></span>}
      {s.worst_agent && s.worst_agent !== s.best_agent && <span className="text-gray-400">Worst: <span className="text-red-400">{s.worst_agent}</span></span>}
      <span className="text-gray-600">{s.total_deterministic_failures} deterministic failures</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ReliabilityPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const { data: leaderboard, isLoading, refetch } = useReliabilityLeaderboard(50);
  const { data: summary } = useReliabilitySummary();
  const { data: selectedHistory } = useAgentReliabilityHistory(selectedAgent, 30);
  const { mutate: compute, isPending: computing } = useTriggerReliabilityCompute();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <div>
          <h1 className="text-base font-semibold text-white">Agent Reliability Scorecard</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Composite 0-100 health score per agent — fail rate, cost, determinism, trend
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => compute()}
            disabled={computing}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            {computing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            Recompute
          </button>
          <button onClick={() => refetch()} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Summary */}
      {summary && <SummaryBanner s={summary} />}

      {/* Two-pane */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: leaderboard */}
        <div className="w-96 border-r border-gray-800 overflow-y-auto shrink-0">
          {isLoading && (
            <div className="flex items-center justify-center h-32 text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading…
            </div>
          )}
          {!isLoading && (!leaderboard || leaderboard.length === 0) && (
            <div className="flex flex-col items-center justify-center h-48 text-gray-500 gap-2">
              <Shield className="w-8 h-8 text-gray-700" />
              <p className="text-sm">No scores yet</p>
              <p className="text-xs text-gray-600">Click Recompute to score all agents</p>
            </div>
          )}
          {leaderboard?.map((row) => (
            <AgentRow
              key={row.agent_name}
              row={row}
              selected={row.agent_name === selectedAgent}
              onSelect={() => setSelectedAgent(row.agent_name)}
              history={
                row.agent_name === selectedAgent
                  ? (selectedHistory ?? [])
                  : []
              }
            />
          ))}
        </div>

        {/* Right: detail */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {selectedAgent ? (
            <AgentPanel agentName={selectedAgent} />
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 gap-3 text-gray-600">
              <Activity className="w-10 h-10 text-gray-800" />
              <p className="text-sm">Select an agent to see its score breakdown</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
