"""
PR-comment markdown formatter for the regression-CI report.

Produces a GitHub-flavored Markdown body that the `zroky/regression-ci@v1`
GitHub Action posts on the PR. Design constraints:

  - **Skimmable in 5 seconds** — verdict + numbers above the fold.
  - **Stable hidden marker** — `<!-- zroky-regression-ci -->` so the
    Action can find and *edit* the prior comment on subsequent runs
    instead of stacking duplicates.
  - **Deterministic** — same report → same markdown bytes. Easy to
    diff in golden snapshot tests.
  - **No HTML beyond the marker and `<details>`** — GitHub strips most
    HTML in PR comments.

This module is pure-functional. It takes a `RegressionCIReport` and
returns a string. No I/O.
"""
from __future__ import annotations

from typing import Iterable

from app.services.regression_ci.models import (
    BlastRadiusCategory,
    DiffVerdict,
    RegressionCIReport,
    RegressionCluster,
    SampleStratum,
)

# Hidden marker so the GitHub Action can find + replace its prior comment.
# DO NOT change this string — older Actions in customer repos look for it.
COMMENT_MARKER: str = "<!-- zroky-regression-ci -->"

# Optional dashboard base URL placeholder. The orchestrator can replace
# `{DASHBOARD_BASE}` after formatting to keep this module dependency-free.
_DASHBOARD_BASE = "{DASHBOARD_BASE}"


# ── public API ──────────────────────────────────────────────────────────────


def format_markdown(report: RegressionCIReport, *, dashboard_base: str = "") -> str:
    """Render a `RegressionCIReport` as a PR-comment markdown body.

    `dashboard_base` is the URL prefix for links into the Zroky dashboard
    (e.g. `https://zroky.com`). Empty string yields placeholder text
    that the customer can still copy-paste.
    """
    lines: list[str] = [COMMENT_MARKER, ""]

    # Header — verdict emoji + headline number.
    lines.extend(_header(report))
    lines.append("")

    # Stats table.
    lines.extend(_stats_table(report))
    lines.append("")

    # Blast radius + sampling provenance.
    lines.extend(_blast_radius_section(report))
    lines.append("")

    # Wedge 4 — Cost-of-failure attribution. Rendered above clusters
    # because the dollar number is what executives skim for. Skipped
    # silently when no outcome events exist for the project.
    if report.outcome_attribution:
        lines.extend(_outcome_attribution_section(report))
        lines.append("")

    if report.failed_goldens or report.warn_goldens or report.not_verified_reasons:
        lines.extend(_golden_gate_section(report))
        lines.append("")

    # Clusters (top 5 only — capped at the model layer).
    if report.clusters:
        lines.extend(_clusters_section(report))
        lines.append("")

    # Sampling realised counts (collapsed by default).
    lines.extend(_stratification_details(report))
    lines.append("")

    # Notes — under-fill warnings, stub-mode notice, etc.
    if report.notes:
        lines.extend(_notes_section(report))
        lines.append("")

    # Footer — link to full run.
    lines.extend(_footer(report, dashboard_base or _DASHBOARD_BASE))

    return "\n".join(lines).rstrip() + "\n"


# ── section builders ────────────────────────────────────────────────────────


def _header(report: RegressionCIReport) -> list[str]:
    if report.verdict == "warn":
        emoji = "WARN"
        headline = "Replay CI warned"
        return [
            f"## {emoji} {headline}",
            "",
            (
                "Only non-blocking or flaky Golden evidence failed. "
                f"Blocking gate threshold: {_pct(report.threshold)}."
            ),
        ]
    if report.verdict == "not_verified":
        emoji = "NOT VERIFIED"
        headline = "Replay CI could not prove safety"
        return [
            f"## {emoji} {headline}",
            "",
            (
                "No trusted blocking Golden proof was available, or required "
                "proof was incomplete. Treat this as a blocked required check."
            ),
        ]
    if report.verdict == "pass":
        emoji = "✅"
        headline = "Replay CI passed"
    elif report.verdict == "fail":
        emoji = "📉"
        headline = "Replay CI regressed"
    else:
        emoji = "⚠️"
        headline = "Replay CI errored"

    return [
        f"## {emoji} {headline}",
        "",
        (
            f"**{report.regressed_count} of {report.trace_count}** replays "
            f"regressed ({_pct(report.regression_rate)}). "
            f"Threshold: {_pct(report.threshold)}."
        ),
    ]


def _stats_table(report: RegressionCIReport) -> list[str]:
    return [
        "| metric | value |",
        "|---|---|",
        f"| **Verdict** | `{report.verdict}` |",
        f"| **Regression rate** | {_pct(report.regression_rate)} ({report.regressed_count} / {report.trace_count}) |",
        f"| **Error rate** | {_pct(report.error_rate)} ({report.error_count}) |",
        f"| **Judge invocations (Tier 3)** | {report.judge_used_count} |",
        f"| **Cost** | ${report.cost_usd:.2f} |",
        f"| **Duration** | {report.duration_seconds}s |",
    ]


def _blast_radius_section(report: RegressionCIReport) -> list[str]:
    br = report.blast_radius
    category_label = _humanize_category(br.category)
    source_label = _humanize_source(br.source)

    lines = [
        "### Blast radius",
        "",
        f"- **Category**: `{br.category}` ({category_label})",
        f"- **Source**: {source_label} (confidence {br.confidence:.2f})",
    ]
    if br.target:
        lines.append(f"- **Target**: `{br.target}`")
    if br.files:
        # Show first 10; collapse the rest into a count.
        shown = list(br.files[:10])
        extra = len(br.files) - len(shown)
        files_md = ", ".join(f"`{f}`" for f in shown)
        if extra > 0:
            files_md += f" _(+{extra} more)_"
        lines.append(f"- **Files**: {files_md}")
    lines.append("")
    lines.append(f"_Sample plan_: **{report.sample_spec.target_total} traces** "
                 f"(default for `{br.category}`).")
    return lines


def _outcome_attribution_section(report: RegressionCIReport) -> list[str]:
    """Render the Wedge 4 cost-of-failure attribution snapshot.

    Output goal: a CFO can skim two lines and answer
    "should this PR merge tonight?" in dollar terms. Numbers are
    extrapolations, not actuarial — we say so honestly via the
    "estimated" qualifier.
    """
    snap = report.outcome_attribution or {}
    cost_30d = float(snap.get("outcome_cost_30d_usd") or 0.0)
    failed_30d = int(snap.get("failed_call_count_30d") or 0)
    risk = float(snap.get("estimated_monthly_risk_usd") or 0.0)
    regressed = int(snap.get("regressed_in_pr") or 0)

    if regressed > 0 and risk > 0.0:
        headline = (
            f"💰 **Estimated risk if merged**: ~${risk:,.0f}/mo "
            f"({regressed} regressed traces × ${(risk / regressed):,.2f}/trace "
            f"based on the last 30 days of outcomes)."
        )
    else:
        headline = (
            "💰 **Cost-of-failure context** — this PR adds no measurable "
            "risk on top of historical outcomes."
        )

    return [
        "### Cost-of-failure attribution",
        "",
        headline,
        "",
        f"- Past 30d outcome cost on this project: **${cost_30d:,.0f}**",
        f"- Past 30d diagnosed failed calls: **{failed_30d:,}**",
        "- Method: linear extrapolation; treat as a directional estimate, not an SLA.",
    ]


def _golden_gate_section(report: RegressionCIReport) -> list[str]:
    lines = ["### Golden gate evidence", ""]
    if report.failed_goldens:
        lines.append("**Blocking Golden failures**")
        for item in report.failed_goldens[:10]:
            lines.append(_golden_item_line(item))
        lines.append("")
    if report.warn_goldens:
        lines.append("**Warning-only Golden failures**")
        for item in report.warn_goldens[:10]:
            lines.append(_golden_item_line(item))
        lines.append("")
    if report.not_verified_reasons:
        lines.append("**Not verified reasons**")
        for reason in report.not_verified_reasons[:10]:
            lines.append(f"- {reason}")
    return lines


def _golden_item_line(item: dict | object) -> str:
    if not isinstance(item, dict):
        return f"- {item}"
    name = str(item.get("golden_name") or item.get("name") or "Golden")
    trace_id = str(item.get("golden_trace_id") or item.get("trace_id") or "")
    assertion = str(item.get("assertion") or item.get("status") or "failed")
    replay_mode = str(item.get("replay_mode") or "unknown")
    recommendation = str(
        item.get("recommended_fix") or item.get("recommended_next_action") or ""
    ).strip()
    suffix = f" Suggested fix: {recommendation}" if recommendation else ""
    trace_part = f" trace `{trace_id}`" if trace_id else ""
    return f"- **{name}**{trace_part}: `{assertion}` via `{replay_mode}`.{suffix}"


def _clusters_section(report: RegressionCIReport) -> list[str]:
    """Show top regression clusters. Each cluster gets a one-liner; the
    sample input is folded into a `<details>` to keep the comment compact."""
    lines = [
        f"### Top {len(report.clusters)} regression cluster"
        + ("s" if len(report.clusters) > 1 else ""),
        "",
    ]
    for i, c in enumerate(report.clusters, 1):
        kw = " · ".join(c.keywords) if c.keywords else "—"
        lines.append(
            f"{i}. **{c.label}** — {c.size} trace"
            + ("s" if c.size != 1 else "")
            + f" · keywords: {kw}"
        )
        lines.append("   <details><summary>Sample input</summary>")
        lines.append("")
        lines.append("   ```")
        # Indent sample input so the closing fence is also indented (keeps
        # GitHub renderer happy inside the <details> block).
        for line in c.sample_input.splitlines() or [c.sample_input]:
            lines.append(f"   {line}")
        lines.append("   ```")
        lines.append("")
        lines.append(f"   <sub>Sample trace: `{c.sample_trace_id}`</sub>")
        lines.append("   </details>")
    return lines


def _stratification_details(report: RegressionCIReport) -> list[str]:
    s = report.stratification_realised
    return [
        "<details><summary>Sampling stratification (realised)</summary>",
        "",
        "| stratum | count |",
        "|---|---|",
        f"| `{SampleStratum.PASS_HISTORY}` (catches new regressions) | {s.pass_history} |",
        f"| `{SampleStratum.FAIL_HISTORY}` (catches regression-recovery) | {s.fail_history} |",
        f"| `{SampleStratum.RARE_CLUSTER}` (edge cases) | {s.rare_cluster} |",
        f"| `{SampleStratum.RECENT_24H}` (freshness) | {s.recent_24h} |",
        f"| **realised total** | **{s.realised_total}** |",
        "",
        "</details>",
    ]


def _notes_section(report: RegressionCIReport) -> list[str]:
    lines = ["### Notes", ""]
    for note in report.notes:
        lines.append(f"- {note}")
    return lines


def _footer(report: RegressionCIReport, dashboard_base: str) -> list[str]:
    detail_path = f"/evidence?replay_run_id={report.run_id}"
    if dashboard_base and dashboard_base != _DASHBOARD_BASE:
        link = f"{dashboard_base.rstrip('/')}{detail_path}"
        link_md = f"[Inspect run in Zroky dashboard →]({link})"
    else:
        link_md = (
            f"Inspect run in Zroky dashboard: `{detail_path}` "
            f"(set `dashboard_base` to enable links)"
        )
    return [
        "---",
        link_md,
        f"<sub>run_id: `{report.run_id}` · "
        f"git_sha: `{report.git_sha or '—'}` · "
        f"schema: `{report.schema_version}`</sub>",
    ]


# ── small helpers ───────────────────────────────────────────────────────────


def _pct(x: float) -> str:
    """Format 0.0234 as '2.34%' deterministically."""
    return f"{x * 100:.2f}%"


def _humanize_category(category: str) -> str:
    return {
        BlastRadiusCategory.SYSTEM_PROMPT: "touches the system prompt — broad blast",
        BlastRadiusCategory.MODEL_SWAP: "switches model — broad blast",
        BlastRadiusCategory.MODEL_PARAMS: "tunes temperature/top_p/seed",
        BlastRadiusCategory.RETRIEVAL_CONFIG: "changes RAG configuration",
        BlastRadiusCategory.TOOL_DEFINITION: "modifies a tool definition",
        BlastRadiusCategory.TOOL_PROMPT: "edits a tool's prompt — narrow blast",
        BlastRadiusCategory.UNKNOWN: "unclassified — conservative sample",
    }.get(category, category)


def _humanize_source(source: str) -> str:
    return {
        "declared": "declared in PR body / .zroky.yml",
        "auto_detected": "auto-detected from changed files",
        "override": "set manually by operator",
    }.get(source, source)
