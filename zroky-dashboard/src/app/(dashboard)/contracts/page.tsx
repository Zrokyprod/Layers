"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";

import {
  importGoldenContracts,
  listGoldenSets,
  listRegressionContracts,
  type GoldenSetView,
  type RegressionContractView,
  type RegressionContractVersionView,
} from "@/lib/api";

type ContractsTab = "contracts" | "fixtures";

function statusClass(status: string): string {
  if (status === "active") return "badge-green";
  if (status === "draft") return "badge-yellow";
  if (status === "quarantined") return "badge-red";
  return "badge-gray";
}

function severityClass(severity: string): string {
  if (severity === "critical" || severity === "high") return "badge-red";
  if (severity === "medium") return "badge-yellow";
  return "badge-gray";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

function activeVersion(contract: RegressionContractView): RegressionContractVersionView | null {
  return contract.versions.find((version) => version.id === contract.active_version_id) ?? contract.versions[0] ?? null;
}

function proofLabel(contract: RegressionContractView, version: RegressionContractVersionView | null): string {
  if (contract.status === "active" && version?.approved_at) return "Approved";
  if (!version) return "No version";
  if (!version.fixture_set_id || !version.baseline_release_id) return "Missing pins";
  return "Needs approval";
}

function ContractsTable({ contracts }: { contracts: RegressionContractView[] }) {
  if (contracts.length === 0) {
    return (
      <div className="gm-empty">
        <ShieldCheck aria-hidden="true" />
        <strong>No contracts yet</strong>
        <span>Create one from a confirmed incident after baseline reproduction and candidate replay proof.</span>
      </div>
    );
  }

  return (
    <div className="gm-table-wrap">
      <table className="gm-table">
        <thead>
          <tr>
            <th>Contract</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Version</th>
            <th>Proof</th>
            <th>Fixture</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {contracts.map((contract) => {
            const version = activeVersion(contract);
            return (
              <tr key={contract.id} className="gm-table-row">
                <td>
                  <div className="gm-set-cell">
                    <Link href={`/contracts/${contract.id}`}>
                      <strong>{contract.name}</strong>
                    </Link>
                    <span>{contract.description || contract.id}</span>
                  </div>
                </td>
                <td><span className={`alert-cat-badge ${severityClass(contract.severity)}`}>{contract.severity}</span></td>
                <td><span className={`alert-cat-badge ${statusClass(contract.status)}`}>{contract.status}</span></td>
                <td>{version ? `v${version.version_number}` : "None"}</td>
                <td>
                  <Link href={`/contracts/${contract.id}`}>{proofLabel(contract, version)}</Link>
                </td>
                <td>
                  {version?.fixture_set_id ? (
                    <Link href={`/goldens/${version.fixture_set_id}`}>Open fixture</Link>
                  ) : (
                    "Not pinned"
                  )}
                </td>
                <td>{formatDate(contract.updated_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FixturesTable({ fixtures }: { fixtures: GoldenSetView[] }) {
  if (fixtures.length === 0) {
    return (
      <div className="gm-empty">
        <Database aria-hidden="true" />
        <strong>No fixtures yet</strong>
        <span>Fixtures appear after replay captures pinned trace and tool evidence. They stay evidence-only until a Contract version is approved.</span>
      </div>
    );
  }

  return (
    <div className="gm-table-wrap">
      <table className="gm-table">
        <thead>
          <tr>
            <th>Fixture set</th>
            <th>Traces</th>
            <th>CI</th>
            <th>Updated</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          {fixtures.map((fixture) => (
            <tr key={fixture.id} className="gm-table-row">
              <td>
                <div className="gm-set-cell">
                  <Link href={`/goldens/${fixture.id}`}>{fixture.name}</Link>
                  <span>{fixture.description || fixture.id}</span>
                </div>
              </td>
              <td>{fixture.trace_count}</td>
              <td>
                <span className={`alert-cat-badge ${fixture.blocks_ci ? "badge-green" : "badge-gray"}`}>
                  {fixture.blocks_ci ? "Blocks CI" : "Evidence only"}
                </span>
              </td>
              <td>{formatDate(fixture.updated_at)}</td>
              <td><Link href={`/goldens/${fixture.id}`}>Details</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ContractsPage() {
  const [tab, setTab] = useState<ContractsTab>("contracts");
  const [search, setSearch] = useState("");
  const queryClient = useQueryClient();
  const contractsQuery = useQuery({
    queryKey: ["regression-contracts"],
    queryFn: ({ signal }) => listRegressionContracts({ limit: 100 }, signal),
  });
  const fixturesQuery = useQuery({
    queryKey: ["golden-sets"],
    queryFn: ({ signal }) => listGoldenSets({ limit: 100 }, signal),
  });
  const importMutation = useMutation({
    mutationFn: () => importGoldenContracts(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["regression-contracts"] });
    },
  });

  const contracts = useMemo(() => contractsQuery.data ?? [], [contractsQuery.data]);
  const fixtures = useMemo(() => fixturesQuery.data?.items ?? [], [fixturesQuery.data?.items]);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredContracts = contracts.filter((contract) => {
    if (!normalizedSearch) return true;
    return [contract.name, contract.description, contract.status, contract.severity, contract.id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedSearch));
  });
  const filteredFixtures = fixtures.filter((fixture) => {
    if (!normalizedSearch) return true;
    return [fixture.name, fixture.description, fixture.id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedSearch));
  });
  const activeCount = contracts.filter((contract) => contract.status === "active").length;
  const draftCount = contracts.filter((contract) => contract.status === "draft").length;

  return (
    <div className="goldens-mvp">
      <section className="gm-hero">
        <div>
          <div className="gm-eyebrow">
            <ShieldCheck aria-hidden="true" />
            Regression contracts
          </div>
          <h1>Contracts</h1>
          <p>Activated incident contracts and the fixture evidence used by repository replay and CI gates.</p>
        </div>
        <div className="gm-hero-actions">
          <button
            type="button"
            className="btn btn-soft"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ["regression-contracts"] });
              void queryClient.invalidateQueries({ queryKey: ["golden-sets"] });
            }}
          >
            <RefreshCw aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={importMutation.isPending}
            onClick={() => importMutation.mutate()}
          >
            <Upload aria-hidden="true" />
            {importMutation.isPending ? "Importing..." : "Import fixtures"}
          </button>
        </div>
      </section>

      <section className="gm-kpi-grid" aria-label="Contract summary">
        <div className="gm-kpi-card is-active">
          <span>Active</span>
          <strong>{activeCount}</strong>
          <small>Blocking contract versions</small>
        </div>
        <div className="gm-kpi-card">
          <span>Draft</span>
          <strong>{draftCount}</strong>
          <small>Need pinned proof and approval</small>
        </div>
        <div className="gm-kpi-card">
          <span>Fixtures</span>
          <strong>{fixtures.length}</strong>
          <small>Fixture evidence sets</small>
        </div>
      </section>

      {contractsQuery.error || fixturesQuery.error || importMutation.error ? (
        <div className="gm-notice">
          <AlertTriangle aria-hidden="true" />
          <strong>Contracts data incomplete.</strong>
          <span>{contractsQuery.error?.message ?? fixturesQuery.error?.message ?? importMutation.error?.message}</span>
        </div>
      ) : null}

      {importMutation.data ? (
        <div className="gm-notice-muted">
          <CheckCircle2 aria-hidden="true" />
          <strong>{importMutation.data.imported_count} contract version{importMutation.data.imported_count === 1 ? "" : "s"} imported.</strong>
          <span>Imported versions stay draft until baseline, candidate SHA, fixture, evaluator, and admin approval are pinned.</span>
        </div>
      ) : null}

      <section className="gm-table-section">
        <header className="gm-section-header">
          <div className="gm-table-tools">
            <div className="gm-row-actions" role="tablist" aria-label="Contracts workspace">
              <button type="button" className={`btn btn-sm ${tab === "contracts" ? "btn-primary" : "btn-soft"}`} onClick={() => setTab("contracts")}>
                Contracts
              </button>
              <button type="button" className={`btn btn-sm ${tab === "fixtures" ? "btn-primary" : "btn-soft"}`} onClick={() => setTab("fixtures")}>
                Fixtures
              </button>
            </div>
            <label>
              <Search aria-hidden="true" />
              <input
                className="input"
                aria-label="Search contracts or fixtures"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search"
              />
            </label>
          </div>
        </header>

        {tab === "contracts" ? (
          <ContractsTable contracts={filteredContracts} />
        ) : (
          <FixturesTable fixtures={filteredFixtures} />
        )}
      </section>
    </div>
  );
}
