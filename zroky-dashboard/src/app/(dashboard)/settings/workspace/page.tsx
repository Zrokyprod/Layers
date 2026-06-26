"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Check,
  Copy,
  FolderOpen,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { useMyProjects, useProjectSettings } from "@/lib/hooks";
import { formatDateTime, safeString } from "@/lib/format";
import { useDashboardStore } from "@/lib/store";

function roleLabel(value: string | null | undefined): string {
  const normalized = value?.trim();
  if (!normalized) return "Member";
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function compactIdentifier(value: string | null | undefined): string {
  const normalized = value?.trim();
  if (!normalized) return "Unavailable";
  if (normalized.length <= 22) return normalized;
  return `${normalized.slice(0, 12)}...${normalized.slice(-6)}`;
}

export default function WorkspaceSettingsPage() {
  const selectedProject = useDashboardStore((state) => state.selectedProject);
  const projectQuery = useProjectSettings();
  const projectsQuery = useMyProjects();
  const [copied, setCopied] = useState(false);

  const project = projectQuery.data ?? null;
  const memberships = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const projectId = project?.project_id ?? selectedProject;
  const membership = useMemo(
    () => memberships.find((item) => item.project_id === projectId) ?? null,
    [memberships, projectId],
  );
  const workspaceName = safeString(project?.name ?? membership?.project_name, "Project unavailable");
  const projectSource = project?.project_id ? "Backend" : selectedProject ? "Store fallback" : "Missing";
  const loading = projectQuery.isLoading || projectsQuery.isLoading;

  async function copyProjectId() {
    if (!projectId) return;
    try {
      await navigator.clipboard.writeText(projectId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="page-content workspace-settings-page">
      <section className="settings-summary-grid">
        <article className="panel settings-summary-card">
          <FolderOpen aria-hidden="true" />
          <span>Workspace</span>
          <strong>{workspaceName}</strong>
          <small>{projectSource} project context.</small>
        </article>
        <article className="panel settings-summary-card">
          <ShieldCheck aria-hidden="true" />
          <span>Status</span>
          <strong>{project?.is_active === false || membership?.is_active === false ? "Inactive" : "Active"}</strong>
          <small>{loading ? "Loading project state." : "Used by capture, billing, and member access."}</small>
        </article>
        <article className="panel settings-summary-card">
          <UserRound aria-hidden="true" />
          <span>Your role</span>
          <strong>{roleLabel(membership?.role)}</strong>
          <small>{membership ? "Role comes from project membership." : "Membership details are not loaded."}</small>
        </article>
        <article className="panel settings-summary-card">
          <RefreshCw aria-hidden="true" />
          <span>Updated</span>
          <strong>{formatDateTime(project?.updated_at ?? membership?.updated_at)}</strong>
          <small>Latest project metadata timestamp.</small>
        </article>
      </section>

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>Workspace identity</h3>
            <p>Basic project metadata used across the dashboard. Operational proof and alert routes live outside Settings.</p>
          </div>
          <div className="actions">
            <Link href="/projects" className="btn btn-soft">
              Open projects
            </Link>
            <Link href="/settings/team" className="btn btn-soft">
              Manage members
            </Link>
          </div>
        </header>

        <div className="list">
          <div className="list-row">
            <div className="list-main">
              <strong>Project name</strong>
              <span>{workspaceName}</span>
            </div>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Project ID</strong>
              <span className="mono">{compactIdentifier(projectId)}</span>
            </div>
            <button type="button" className="btn btn-soft btn-sm" onClick={() => void copyProjectId()} disabled={!projectId}>
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              {copied ? "Copied" : "Copy project ID"}
            </button>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Owner reference</strong>
              <span className="mono">{compactIdentifier(project?.owner_ref)}</span>
            </div>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Created</strong>
              <span>{formatDateTime(project?.created_at ?? membership?.created_at)}</span>
            </div>
          </div>
          <div className="list-row">
            <div className="list-main">
              <strong>Project source</strong>
              <span>{projectSource}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="panel settings-control-panel">
        <header className="panel-header">
          <div>
            <h3>What belongs here</h3>
            <p>Workspace Settings stays limited to project identity. Connectors, outcome proof, and alert routing stay in their own modules.</p>
          </div>
        </header>
        <div className="settings-workspace-rules" aria-label="Workspace settings boundaries">
          <div>
            <strong>Keep in Settings</strong>
            <span>Project name, project ID, member context, billing context.</span>
          </div>
          <div>
            <strong>Use Connectors</strong>
            <span>GitHub, Slack, ledger, and customer-record setup.</span>
          </div>
          <div>
            <strong>Use Evidence</strong>
            <span>Evidence Packs, outcome reconciliation, and exportable proof.</span>
          </div>
        </div>
      </section>
    </div>
  );
}
