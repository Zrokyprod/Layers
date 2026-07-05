"use client";

import {
  TOOL_CATALOG,
  TOOL_CATEGORY_ICONS,
  TOOL_STATUS_LABELS,
  TOOL_SUMMARY_ICONS,
  type ToolCatalogStatus,
} from "@/lib/tool-catalog";

function statusTone(status: ToolCatalogStatus): "ok" | "warn" | "neutral" {
  if (status === "available") return "ok";
  if (status === "fallback") return "warn";
  return "neutral";
}

export default function ToolCatalogPage() {
  const grouped = Object.entries(
    TOOL_CATALOG.reduce<Record<string, typeof TOOL_CATALOG>>((acc, tool) => {
      acc[tool.category] = [...(acc[tool.category] ?? []), tool];
      return acc;
    }, {}),
  );
  const availableCount = TOOL_CATALOG.filter((tool) => tool.status === "available").length;
  const nativeCount = TOOL_CATALOG.filter((tool) => tool.status !== "fallback").length;
  const fallbackCount = TOOL_CATALOG.filter((tool) => tool.status === "fallback").length;
  const AvailableIcon = TOOL_SUMMARY_ICONS.available;
  const RoadmapIcon = TOOL_SUMMARY_ICONS.roadmap;
  const FallbackIcon = TOOL_SUMMARY_ICONS.fallback;

  return (
    <div className="owner-page owner-tool-page">
      <div className="owner-page-header">
        <div>
          <h2 className="owner-page-title">Connector Catalog</h2>
          <p className="hint">Source-of-record connectors first. Generic REST stays a custom fallback.</p>
        </div>
      </div>

      <div className="owner-command-grid owner-tool-summary-grid">
        <div className="owner-command-card owner-command-card-ok">
          <span className="owner-command-icon" aria-hidden="true"><AvailableIcon size={18} /></span>
          <span className="owner-stat-label">Available connectors</span>
          <strong>{availableCount.toLocaleString()}</strong>
          <p>Ready connector families for governed action evidence.</p>
        </div>
        <div className="owner-command-card owner-command-card-neutral">
          <span className="owner-command-icon" aria-hidden="true"><RoadmapIcon size={18} /></span>
          <span className="owner-stat-label">Native catalog</span>
          <strong>{nativeCount.toLocaleString()}</strong>
          <p>Native-first catalog, grouped by operational workflow.</p>
        </div>
        <div className="owner-command-card owner-command-card-warn">
          <span className="owner-command-icon" aria-hidden="true"><FallbackIcon size={18} /></span>
          <span className="owner-stat-label">Fallback</span>
          <strong>{fallbackCount.toLocaleString()}</strong>
          <p>Generic REST stays available for custom systems only.</p>
        </div>
      </div>

      <div className="owner-tool-category-list">
        {grouped.map(([category, tools]) => {
          const Icon = TOOL_CATEGORY_ICONS[category] ?? TOOL_SUMMARY_ICONS.default;
          return (
            <section key={category} className="panel">
              <div className="panel-header">
                <h3>
                  <Icon size={17} aria-hidden="true" />
                  {category}
                </h3>
                <span className="panel-header-note">{tools.length} tool{tools.length !== 1 ? "s" : ""}</span>
              </div>
              <div className="owner-tool-grid">
                {tools.map((tool) => (
                  <article key={tool.connectorId} className="owner-tool-card">
                    <div className="owner-tool-card-head">
                      <div>
                        <strong>{tool.name}</strong>
                        <code>{tool.connectorId}</code>
                      </div>
                      <span className={`owner-money-badge owner-money-badge-${statusTone(tool.status)}`}>
                        {TOOL_STATUS_LABELS[tool.status]}
                      </span>
                    </div>
                    <p>{tool.useCase}</p>
                    <small>{tool.proof}</small>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
