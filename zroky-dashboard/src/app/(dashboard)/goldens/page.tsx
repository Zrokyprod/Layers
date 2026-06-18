"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Eye,
  Filter,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { hasGoldensAccess, hasPlanEntitlement, isPaidGoldensPlan, normalizePlanCode } from "@/components/feature-gate";
import { KpiCard, SectionHeader } from "@/components/command-center-primitives";
import {
  createGoldenSet,
  getBillingMe,
  listGoldenSets,
  listReplayRuns,
  runGoldenSet,
  type GoldenSetView,
  type ReplayRunItem,
} from "@/lib/api";
import {
  ciBadgeClass,
  ciBlockingLabel,
  healthBadgeClass,
  healthForSet,
  lastRunLabel,
  latestRunForSet,
  passRateForRuns,
  setMetadataLine,
} from "./golden-utils";

type GoldenFilter = "all" | "blocking" | "review";

function CreateSetPanel({ enabled, onCreated }: { enabled: boolean; onCreated: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const createMutation = useMutation({
    mutationFn: () => createGoldenSet({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: () => {
      setName("");
      setDescription("");
      onCreated();
      void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
    },
  });

  return (
    <section className="panel gm-create-panel" aria-label="Create fixture set">
      <header className="gm-section-header">
        <div>
          <h2>Create set</h2>
          <p>Group verified production behaviors before they protect future CI runs.</p>
        </div>
        {!enabled ? <span className="alert-cat-badge badge-yellow">Locked</span> : null}
      </header>
      <div className="gm-create-grid">
        <label>
          <span>Name</span>
          <input
            aria-label="Fixture set name"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Refund protected flow"
            disabled={!enabled}
          />
        </label>
        <label>
          <span>Description</span>
          <input
            aria-label="Fixture set description"
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Verified refund-agent behavior"
            disabled={!enabled}
          />
        </label>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!enabled || !name.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          {createMutation.isPending ? <Loader2 aria-hidden="true" /> : <Plus aria-hidden="true" />}
          {createMutation.isPending ? "Creating..." : "Create set"}
        </button>
      </div>
      {createMutation.error ? <p className="notif-error">{createMutation.error.message}</p> : null}
    </section>
  );
}

function GoldenSetRow({
  set,
  runs,
  canUseGoldens,
}: {
  set: GoldenSetView;
  runs: ReplayRunItem[];
  canUseGoldens: boolean;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const setRuns = runs.filter((run) => run.golden_set_id === set.id);
  const latestRun = latestRunForSet(runs, set.id);
  const health = healthForSet(set, setRuns);
  const ciLabel = ciBlockingLabel(set, setRuns);
  const runMutation = useMutation({
    mutationFn: () => runGoldenSet(set.id, { trigger: "manual" }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      router.push(`/replay/${created.id}`);
    },
  });

  return (
    <tr className="gm-table-row">
      <td>
        <div className="gm-set-cell">
          <Link href={`/goldens/${set.id}`}>{set.name}</Link>
          <span>{setMetadataLine(set)}</span>
        </div>
      </td>
      <td>{set.trace_count}</td>
      <td>
        <span className="gm-run-label">{lastRunLabel(latestRun)}</span>
      </td>
      <td>
        <span className={`alert-cat-badge ${ciBadgeClass(ciLabel)}`}>{ciLabel}</span>
      </td>
      <td>
        <span className={`alert-cat-badge ${healthBadgeClass(health)}`}>{health}</span>
      </td>
      <td>
        <div className="gm-row-actions">
          <button
            type="button"
            className="btn btn-soft btn-sm"
            disabled={!canUseGoldens || set.trace_count === 0 || runMutation.isPending}
            onClick={() => runMutation.mutate()}
          >
            {runMutation.isPending ? <Loader2 aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
            {runMutation.isPending ? "Running..." : "Run"}
          </button>
          <Link href={`/goldens/${set.id}`} className="btn btn-soft btn-sm">
            <Eye aria-hidden="true" />
            View
          </Link>
        </div>
      </td>
    </tr>
  );
}

export default function GoldensPage() {
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<GoldenFilter>("all");
  const [selectedSetId, setSelectedSetId] = useState("");
  const queryClient = useQueryClient();
  const billingQuery = useQuery({
    queryKey: ["billing-me"],
    queryFn: ({ signal }) => getBillingMe(signal),
  });
  const setsQuery = useQuery({
    queryKey: ["golden-sets"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 100 }, signal),
  });
  const runsQuery = useQuery({
    queryKey: ["replay-runs", { limit: 100 }],
    queryFn: ({ signal }) => listReplayRuns({ limit: 100 }, signal),
  });

  const sets = useMemo(() => setsQuery.data?.items ?? [], [setsQuery.data?.items]);
  const runs = useMemo(() => runsQuery.data?.items ?? [], [runsQuery.data?.items]);
  const planTemplate = billingQuery.data?.plan_template;
  const planCode = billingQuery.data?.plan_code;
  const explicitGoldensEntitlement = hasPlanEntitlement(planTemplate, "pilot.goldens_basic");
  const canUseGoldens = hasGoldensAccess(planTemplate, planCode);
  const normalizedPlanCode = normalizePlanCode(planCode);
  const isFreeGoldensPlan = normalizedPlanCode === "free" || normalizedPlanCode === "watch";
  const showLockedBanner = !billingQuery.isLoading && !canUseGoldens && isFreeGoldensPlan;
  const showEntitlementWarning =
    !billingQuery.isLoading &&
    !showLockedBanner &&
    (!billingQuery.data || (isPaidGoldensPlan(planCode) && !explicitGoldensEntitlement));
  const entitlementUnavailableTitle = showEntitlementWarning
    ? "Plan entitlement unavailable. Refresh workspace plan or contact admin."
    : undefined;
  const canOperateGoldens = canUseGoldens && !showEntitlementWarning;
  const selectedSet = sets.find((set) => set.id === selectedSetId) ?? null;
  const firstRunnableSet = (selectedSet?.trace_count ? selectedSet : null) ?? sets.find((set) => set.trace_count > 0) ?? sets[0] ?? null;
  const activeGoldens = sets.reduce((sum, set) => sum + set.trace_count, 0);
  const blockingCi = sets.filter((set) => ciBlockingLabel(set, runs.filter((run) => run.golden_set_id === set.id)) === "Blocks CI").length;
  const needReview = sets.filter((set) => healthForSet(set, runs.filter((run) => run.golden_set_id === set.id)) !== "Healthy").length;
  const lastPassRate = passRateForRuns(runs);
  const filteredSets = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return sets.filter((set) => {
      const setRuns = runs.filter((run) => run.golden_set_id === set.id);
      const health = healthForSet(set, setRuns);
      const ciLabel = ciBlockingLabel(set, setRuns);
      if (filter === "blocking" && ciLabel !== "Blocks CI") return false;
      if (filter === "review" && health === "Healthy") return false;
      if (!normalizedSearch) return true;
      return [set.name, set.description, set.id, setMetadataLine(set)]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedSearch));
    });
  }, [filter, runs, search, sets]);
  const runFirstMutation = useMutation({
    mutationFn: () => {
      if (!firstRunnableSet) throw new Error("No fixture set available.");
      return runGoldenSet(firstRunnableSet.id, { trigger: "manual" });
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["replay-runs"] });
      router.push(`/replay/${created.id}`);
    },
  });

  return (
    <div className="goldens-mvp">
      <section className="gm-hero">
        <div>
          <div className="gm-eyebrow">
            <BookOpen aria-hidden="true" />
            Contract fixtures
          </div>
          <h1>Fixtures</h1>
          <p>Verified production behaviors used as Contract evidence and replay fixtures.</p>
        </div>
        <div className="gm-hero-actions">
          <label className="gm-run-select">
            <span>Run set</span>
            <select
              className="input"
              value={selectedSetId}
              onChange={(event) => setSelectedSetId(event.target.value)}
              disabled={!canOperateGoldens || sets.length === 0}
            >
              <option value="">First runnable set</option>
              {sets.map((set) => (
                <option key={set.id} value={set.id} disabled={set.trace_count === 0}>
                  {set.name} - {set.trace_count} traces
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canOperateGoldens || !firstRunnableSet || firstRunnableSet.trace_count === 0 || runFirstMutation.isPending}
            title={entitlementUnavailableTitle}
            onClick={() => runFirstMutation.mutate()}
          >
            {runFirstMutation.isPending ? <Loader2 aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
            {runFirstMutation.isPending ? "Running..." : "Run fixture set"}
            <ArrowRight aria-hidden="true" />
          </button>
          <button
            type="button"
            className="btn btn-soft"
            disabled={showEntitlementWarning}
            title={entitlementUnavailableTitle}
            onClick={() => setShowCreate((value) => !value)}
          >
            <Plus aria-hidden="true" />
            Create set
          </button>
        </div>
      </section>

      {showLockedBanner ? (
        <section className="gm-notice" aria-label="Fixtures locked">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>Fixtures locked</strong>
            <p>Upgrade to Starter to create protected flows from verified replay evidence.</p>
          </div>
          <Link href="/settings/billing" className="btn btn-soft">Upgrade</Link>
        </section>
      ) : null}

      {showEntitlementWarning ? (
        <section className="gm-notice gm-notice-muted" aria-label="Fixtures entitlement unavailable">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>Fixtures entitlement unavailable</strong>
            <p>Refresh workspace plan or contact admin.</p>
          </div>
        </section>
      ) : null}

      {showCreate && !showEntitlementWarning ? <CreateSetPanel enabled={canUseGoldens} onCreated={() => setShowCreate(false)} /> : null}

      <section className="fi-kpi-grid gm-kpi-grid" aria-label="Fixture KPI summary">
        <KpiCard
          icon={<BookOpen aria-hidden="true" />}
          label="Active fixtures"
          value={String(activeGoldens)}
          helper="Loaded protected traces"
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <KpiCard
          icon={<ShieldCheck aria-hidden="true" />}
          label="Blocking CI"
          value={String(blockingCi)}
          helper="Healthy blocking sets"
          active={filter === "blocking"}
          onClick={() => setFilter("blocking")}
        />
        <KpiCard
          icon={<AlertTriangle aria-hidden="true" />}
          label="Need review"
          value={String(needReview)}
          helper="Empty, flaky, drift, or failed"
          active={filter === "review"}
          onClick={() => setFilter("review")}
        />
        <KpiCard
          icon={<Sparkles aria-hidden="true" />}
          label="Last pass rate"
          value={lastPassRate}
          helper="Recent fixture runs"
        />
      </section>

      <section className="gm-table-section">
        <SectionHeader
          title="Fixture sets"
          description="Protected flows, run status, and CI blocking visibility."
          action={
            <div className="gm-table-tools">
              <label>
                <Search aria-hidden="true" />
                <input
                  className="input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search fixture sets..."
                />
              </label>
              <span className="gm-trust-copy">
                <Filter aria-hidden="true" />
                {filter === "all" ? "All sets" : filter}
              </span>
              <span className="gm-trust-copy">
                <Sparkles aria-hidden="true" />
                Only verified replay fixes can become active Contracts.
              </span>
            </div>
          }
        />

        {setsQuery.isLoading ? (
          <div className="gm-empty">
            <Loader2 aria-hidden="true" />
            <strong>Loading fixture sets...</strong>
          </div>
        ) : sets.length === 0 ? (
          <div className="gm-empty">
            <BookOpen aria-hidden="true" />
            <strong>No fixtures yet</strong>
            <p>Create a fixture from a verified replay, then approve a Contract to protect that flow in future CI runs.</p>
            {showEntitlementWarning ? (
              <p>Replay and fixture creation require an active Starter or Pro entitlement.</p>
            ) : canUseGoldens ? (
              <Link href="/replay" className="btn btn-primary">Go to Replay</Link>
            ) : null}
          </div>
        ) : filteredSets.length === 0 ? (
          <div className="gm-empty">
            <Search aria-hidden="true" />
            <strong>No matching fixtures</strong>
            <p>Clear search or switch KPI filters.</p>
          </div>
        ) : (
          <div className="gm-table-wrap">
            <table className="gm-table">
              <thead>
                <tr>
                  <th>Fixture set</th>
                  <th>Traces</th>
                  <th>Last run</th>
                  <th>CI blocking</th>
                  <th>Health</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredSets.map((set) => (
                  <GoldenSetRow key={set.id} set={set} runs={runs} canUseGoldens={canUseGoldens} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
