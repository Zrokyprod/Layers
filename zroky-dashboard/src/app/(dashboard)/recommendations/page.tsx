"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  DollarSign,
  EyeOff,
  Lightbulb,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  Wrench,
} from "lucide-react";
import {
  useRecommendations,
  useRecSummary,
  useUpdateRecStatus,
  useGenerateRecommendations,
} from "@/lib/hooks";
import type { RecView } from "@/lib/api";

// ── Priority badge ────────────────────────────────────────────────────────────

const PRIORITY_COLORS: Record<string, string> = {
  critical: "bg-red-950/60 text-red-300 border-red-800/60",
  high: "bg-orange-950/60 text-orange-300 border-orange-800/60",
  medium: "bg-yellow-950/60 text-yellow-300 border-yellow-800/60",
  low: "bg-gray-800/60 text-gray-400 border-gray-700/60",
};

function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full border ${PRIORITY_COLORS[priority] ?? PRIORITY_COLORS.low}`}>
      {priority}
    </span>
  );
}

// ── Type icon ─────────────────────────────────────────────────────────────────

function TypeIcon({ type }: { type: string }) {
  const cls = "w-4 h-4 shrink-0";
  if (type === "axis_causal") return <ShieldAlert className={`${cls} text-indigo-400`} />;
  if (type === "determinism_high") return <AlertTriangle className={`${cls} text-red-400`} />;
  if (type === "score_drop") return <TrendingDown className={`${cls} text-orange-400`} />;
  if (type === "cost_spike") return <DollarSign className={`${cls} text-yellow-400`} />;
  return <CircleDot className={`${cls} text-gray-500`} />;
}

// ── Difficulty badge ──────────────────────────────────────────────────────────

function DifficultyBadge({ difficulty }: { difficulty: string | null }) {
  if (!difficulty) return null;
  const colors: Record<string, string> = {
    easy: "text-green-400",
    medium: "text-yellow-400",
    hard: "text-red-400",
  };
  return (
    <span className={`text-xs ${colors[difficulty] ?? "text-gray-400"}`}>
      <Wrench className="w-3 h-3 inline mr-0.5" />{difficulty}
    </span>
  );
}

// ── Status action buttons ─────────────────────────────────────────────────────

function StatusActions({
  rec,
  onAction,
  loading,
}: {
  rec: RecView;
  onAction: (recId: string, status: string) => void;
  loading: boolean;
}) {
  if (rec.status !== "open" && rec.status !== "acknowledged") return null;
  return (
    <div className="flex items-center gap-1.5 mt-2">
      {rec.status === "open" && (
        <button
          onClick={() => onAction(rec.id, "acknowledged")}
          disabled={loading}
          className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-indigo-900/40 border border-indigo-700/40 text-indigo-300 hover:bg-indigo-900/60 disabled:opacity-50 transition-colors"
        >
          <CheckCircle2 className="w-3 h-3" /> Acknowledge
        </button>
      )}
      {rec.status === "acknowledged" && (
        <button
          onClick={() => onAction(rec.id, "resolved")}
          disabled={loading}
          className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-green-900/40 border border-green-700/40 text-green-300 hover:bg-green-900/60 disabled:opacity-50 transition-colors"
        >
          <CheckCircle2 className="w-3 h-3" /> Resolve
        </button>
      )}
      <button
        onClick={() => onAction(rec.id, "dismissed")}
        disabled={loading}
        className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-gray-800/40 border border-gray-700/40 text-gray-400 hover:bg-gray-800/60 disabled:opacity-50 transition-colors"
      >
        <EyeOff className="w-3 h-3" /> Dismiss
      </button>
    </div>
  );
}

// ── Recommendation card ───────────────────────────────────────────────────────

function RecCard({
  rec,
  expanded,
  onToggle,
  onAction,
  actionLoading,
}: {
  rec: RecView;
  expanded: boolean;
  onToggle: () => void;
  onAction: (recId: string, status: string) => void;
  actionLoading: boolean;
}) {
  const isOpen = rec.status === "open" || rec.status === "acknowledged";
  return (
    <div className={`border-b border-gray-800/60 ${rec.status === "dismissed" || rec.status === "resolved" ? "opacity-50" : ""}`}>
      <button
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-gray-800/20 transition-colors"
        onClick={onToggle}
      >
        <TypeIcon type={rec.recommendation_type} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <PriorityBadge priority={rec.priority} />
            <span className="text-xs text-gray-500 font-mono">{rec.agent_name}</span>
            {rec.top_axis && (
              <span className="text-xs text-indigo-400 font-mono">{rec.top_axis}</span>
            )}
            {rec.estimated_monthly_impact_usd != null && rec.estimated_monthly_impact_usd > 0 && (
              <span className="text-xs text-emerald-400 ml-auto">
                ~${rec.estimated_monthly_impact_usd.toFixed(0)}/mo saving
              </span>
            )}
          </div>
          <p className="text-sm text-gray-200">{rec.title}</p>
          {rec.axis_confidence != null && (
            <p className="text-xs text-gray-500 mt-0.5">
              Confidence: <span className="text-indigo-400">{(rec.axis_confidence * 100).toFixed(0)}%</span>
              {rec.health_score_at_generation != null && (
                <> · Health: <span className="text-yellow-400">{Math.round(rec.health_score_at_generation)}</span></>
              )}
            </p>
          )}
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pl-11 space-y-3">
          {rec.detail && (
            <p className="text-xs text-gray-400 leading-relaxed">{rec.detail}</p>
          )}
          {rec.fix_suggestion && (
            <div className="rounded-lg border border-green-900/40 bg-green-950/20 p-3">
              <div className="flex items-center gap-1.5 mb-1 text-green-400">
                <Lightbulb className="w-3.5 h-3.5" />
                <span className="text-xs font-medium">Fix suggestion</span>
                <DifficultyBadge difficulty={rec.fix_difficulty} />
              </div>
              <p className="text-xs text-green-200">{rec.fix_suggestion}</p>
            </div>
          )}
          {isOpen && (
            <StatusActions rec={rec} onAction={onAction} loading={actionLoading} />
          )}
          {rec.status !== "open" && (
            <p className="text-xs text-gray-600 italic">
              Status: {rec.status}{rec.actioned_by ? ` by ${rec.actioned_by}` : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Summary banner ────────────────────────────────────────────────────────────

function SummaryBanner({
  total_open, critical_count, high_count, total_estimated_saving_usd, top_agents,
}: {
  total_open: number;
  critical_count: number;
  high_count: number;
  total_estimated_saving_usd: number;
  top_agents: string[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 px-6 py-3 border-b border-gray-800 bg-gray-900/30 text-xs">
      <span className="text-gray-400">{total_open} open</span>
      {critical_count > 0 && <span className="text-red-400 font-semibold">{critical_count} critical</span>}
      {high_count > 0 && <span className="text-orange-400">{high_count} high</span>}
      {total_estimated_saving_usd > 0 && (
        <span className="text-emerald-400">
          ~${total_estimated_saving_usd.toFixed(0)}/mo potential saving
        </span>
      )}
      {top_agents.length > 0 && (
        <span className="text-gray-500">
          Focus: {top_agents.map((a) => <span key={a} className="text-red-300 font-mono mx-0.5">{a}</span>)}
        </span>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const STATUS_TABS = [
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
];

export default function RecommendationsPage() {
  const [activeStatus, setActiveStatus] = useState("open");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: recs, isLoading, refetch } = useRecommendations({ status: activeStatus, limit: 100 });
  const { data: summary } = useRecSummary();
  const { mutate: updateStatus, isPending: updating } = useUpdateRecStatus();
  const { mutate: generate, isPending: generating } = useGenerateRecommendations();

  const handleAction = (recId: string, status: string) => {
    updateStatus({ recId, status });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <div>
          <h1 className="text-base font-semibold text-white">Reliability Intelligence Queue</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Ranked fix items — causal axis failures, determinism spikes, cost overruns, regressions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => generate()}
            disabled={generating}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Generate
          </button>
          <button onClick={() => refetch()} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Summary */}
      {summary && <SummaryBanner {...summary} />}

      {/* Status tabs */}
      <div className="flex border-b border-gray-800 px-4 pt-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveStatus(tab.value)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeStatus === tab.value
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center h-32 text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading…
          </div>
        )}
        {!isLoading && (!recs || recs.length === 0) && (
          <div className="flex flex-col items-center justify-center h-48 gap-2 text-gray-600">
            <CheckCircle2 className="w-10 h-10 text-gray-800" />
            <p className="text-sm">No {activeStatus} recommendations</p>
            {activeStatus === "open" && (
              <p className="text-xs text-gray-700">Click Generate to analyse agent health data</p>
            )}
          </div>
        )}
        {recs?.map((rec) => (
          <RecCard
            key={rec.id}
            rec={rec}
            expanded={expandedId === rec.id}
            onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
            onAction={handleAction}
            actionLoading={updating}
          />
        ))}
      </div>
    </div>
  );
}
