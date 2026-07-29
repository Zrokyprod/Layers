"use client";

import {
  TOOL_SUMMARY_ICONS,
  toolKindLabel,
  toolStatusLabel,
  toolStatusTone,
} from "@/lib/tool-catalog";
import { useOwnerToolRegistry } from "@/lib/hooks";
import type { OwnerToolRegistryItem, OwnerToolRegistryResponse } from "@/lib/owner-api";

type RegistrySection = {
  id: keyof Pick<OwnerToolRegistryResponse, "runtime_paths" | "verification_connectors" | "native_tool_families">;
  title: string;
  note: string;
  items: OwnerToolRegistryItem[];
};

function listLabel(items: string[], empty = "No action types declared"): string {
  if (items.length === 0) return empty;
  return items.slice(0, 5).join(", ") + (items.length > 5 ? ` +${items.length - 5}` : "");
}

function sectionList(registry: OwnerToolRegistryResponse): RegistrySection[] {
  return [
    {
      id: "runtime_paths",
      title: "Runtime paths",
      note: "Where Zroky can sit in the agent execution path.",
      items: registry.runtime_paths,
    },
    {
      id: "verification_connectors",
      title: "Verification connectors",
      note: "Source-of-record proof paths returned by the backend registry.",
      items: registry.verification_connectors,
    },
    {
      id: "native_tool_families",
      title: "Native tool families",
      note: "Business systems and tool families the product can model natively.",
      items: registry.native_tool_families,
    },
  ];
}

function ToolCard({ item }: { item: OwnerToolRegistryItem }) {
  const supported = listLabel(item.supported_action_types);
  const recommended = listLabel(item.recommended_for_action_types, "No recommendations declared");

  return (
    <article className="owner-tool-card">
      <div className="owner-tool-card-head">
        <div>
          <strong>{item.label}</strong>
          <code>{item.id}</code>
        </div>
        <span className={`owner-money-badge owner-money-badge-${toolStatusTone(item.implementation_status)}`}>
          {toolStatusLabel(item.implementation_status)}
        </span>
      </div>
      <p>{item.description}</p>
      <small>
        {toolKindLabel(item.kind)} / {item.category} / tier {item.launch_tier}
        {item.requires_customer_credentials ? " / customer credentials required" : " / no customer credentials"}
      </small>
      <small>Supported: {supported}</small>
      <small>Recommended: {recommended}</small>
      {item.backend_capability ? <small>Backend capability: {item.backend_capability}</small> : null}
      {item.availability_notes ? <small>{item.availability_notes}</small> : null}
    </article>
  );
}

export default function ToolCatalogPage() {
  const registryQuery = useOwnerToolRegistry();
  const registry = registryQuery.data ?? null;
  const allItems = registry
    ? [...registry.runtime_paths, ...registry.verification_connectors, ...registry.native_tool_families]
    : [];
  const availableCount = allItems.filter((tool) => tool.implementation_status === "available").length;
  const templateCount = allItems.filter((tool) => tool.implementation_status === "template").length;
  const plannedCount = allItems.filter((tool) => tool.implementation_status === "planned").length;
  const AvailableIcon = TOOL_SUMMARY_ICONS.available;
  const TemplateIcon = TOOL_SUMMARY_ICONS.template;
  const PlannedIcon = TOOL_SUMMARY_ICONS.planned;

  return (
    <div className="owner-page owner-tool-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Connector Catalog</h2>
          <p className="hint">Live registry from the backend. No static connector fallback is rendered here.</p>
        </div>
      </div>

      {registryQuery.isLoading ? <div className="panel">Loading live connector registry...</div> : null}
      {registryQuery.error ? (
        <div className="alert-strip alert-strip-error">
          Live connector registry unavailable. Static connector data is intentionally hidden.
        </div>
      ) : null}

      {registry ? (
        <>
          <div className="owner-command-grid owner-tool-summary-grid">
            <div className="owner-command-card owner-command-card-ok">
              <span className="owner-command-icon" aria-hidden="true"><AvailableIcon size={18} /></span>
              <span className="owner-stat-label">Available</span>
              <strong>{availableCount.toLocaleString()}</strong>
              <p>Registry items currently available from the backend.</p>
            </div>
            <div className="owner-command-card owner-command-card-warn">
              <span className="owner-command-icon" aria-hidden="true"><TemplateIcon size={18} /></span>
              <span className="owner-stat-label">Templates</span>
              <strong>{templateCount.toLocaleString()}</strong>
              <p>Configurable templates that still need customer wiring.</p>
            </div>
            <div className="owner-command-card owner-command-card-neutral">
              <span className="owner-command-icon" aria-hidden="true"><PlannedIcon size={18} /></span>
              <span className="owner-stat-label">Planned</span>
              <strong>{plannedCount.toLocaleString()}</strong>
              <p>Registry entries that are visible but not production-ready.</p>
            </div>
          </div>

          <section className="panel">
            <div className="panel-header">
              <h3>Recommended defaults</h3>
              <span className="panel-header-note">Project {registry.project_id}</span>
            </div>
            <div className="owner-tool-grid">
              <article className="owner-tool-card">
                <div className="owner-tool-card-head">
                  <div>
                    <strong>Runtime</strong>
                    <code>{listLabel(registry.recommended.runtime_path_ids, "none")}</code>
                  </div>
                </div>
                <p>{listLabel(registry.recommended.next_steps, "No next steps returned")}</p>
              </article>
              <article className="owner-tool-card">
                <div className="owner-tool-card-head">
                  <div>
                    <strong>Verification connectors</strong>
                    <code>{listLabel(registry.recommended.verification_connector_ids, "none")}</code>
                  </div>
                </div>
                <p>{listLabel(registry.recommended.action_types, "No action type filter applied")}</p>
              </article>
              <article className="owner-tool-card">
                <div className="owner-tool-card-head">
                  <div>
                    <strong>Native families</strong>
                    <code>{listLabel(registry.recommended.native_tool_family_ids, "none")}</code>
                  </div>
                </div>
                <p>Native tool-family recommendations returned by the registry service.</p>
              </article>
            </div>
          </section>

          <div className="owner-tool-category-list">
            {sectionList(registry).map((section) => (
              <section key={section.id} className="panel">
                <div className="panel-header">
                  <h3>{section.title}</h3>
                  <span className="panel-header-note">{section.items.length} live item{section.items.length === 1 ? "" : "s"} / {section.note}</span>
                </div>
                {section.items.length ? (
                  <div className="owner-tool-grid">
                    {section.items.map((tool) => <ToolCard key={`${section.id}:${tool.id}`} item={tool} />)}
                  </div>
                ) : (
                  <p className="hint">Backend returned no items for this section.</p>
                )}
              </section>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
