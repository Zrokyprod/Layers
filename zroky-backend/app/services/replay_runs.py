"""
Replay-runs service — dispatches and reads `replay_runs` + `replay_run_traces`
(plan §6.4, schema from migration 0050).

This service is intentionally separate from the legacy
`app/api/routes/replay.py` + `ReplayJob` model. The legacy surface tracks
**single-fix** replay jobs run by the customer-hosted replay worker; this
new surface tracks **golden-set** batch replays produced by the Pilot tier.
The two are mutually independent and ship side-by-side.

Module 4.2 ships:
  - `dispatch_replay_run()` — synchronously creates a `pending` ReplayRun
    row and returns it. Actual replay execution (which would consume each
    GoldenTrace, re-issue the prompt against current model+config, run the
    judge, and write per-trace ReplayRunTrace rows) is deferred to a
    Celery worker task in a later module. The endpoint contract is therefore
    "202 Accepted; poll GET /v1/replay/runs/{id} for status".
  - `mark_call_as_golden()` — promotes a Call into an existing GoldenSet
    by snapshotting baseline tokens/cost/latency and (optionally) the
    output text supplied by the caller. Powers `POST /v1/calls/{id}/mark-golden`.
  - Reads: `get_replay_run`, `list_replay_runs`, `list_run_traces`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Anomaly,
    Call,
    GoldenTrace,
    ReplayRun,
    ReplayRunTrace,
)
from app.services.goldens import (
    GOLDEN_TRACE_STATUS_ACTIVE,
    add_trace,
    count_traces,
    create_golden_set,
    get_golden_set,
    source_evidence_from_call,
)
from app.services._internal.replay_runs_summary_quota import (
    ReplayQuotaResult,
    build_summary_url,
    check_replay_monthly_quota,
    parse_summary,
)
from app.services._internal.replay_runs_source_context import (
    _one_click_set_name,
    _source_context_from_call,
    _source_context_from_issue,
)
from app.services.issue_projection import issue_projection_from_anomaly

logger = logging.getLogger(__name__)


# ── vocab (must match db CHECK constraints from migration 0050) ──────────────

VALID_TRIGGERS = frozenset({"manual", "github", "schedule"})
VALID_RUN_STATUSES = frozenset({"pending", "running", "pass", "warn", "fail", "not_verified", "error"})
VALID_TRACE_STATUSES = frozenset({"pass", "fail", "not_verified", "error"})

# ── replay-mode vocab (Option A — honesty fix) ───────────────────────────────
#
# "stub"     — default. The executor's default_resolver re-grades the source
#              Call's RECORDED response. Cannot detect regressions from
#              prompt edits / model swaps / RAG changes because no real LLM
#              call is issued. The dashboard MUST surface this so users
#              understand what they're getting.
# "real_llm" — gated by Settings.REPLAY_REAL_LLM_ENABLED + Option B's
#              LiveLlmResolver. Applies `candidate_prompt_override` and/or
#              `candidate_model_override` and issues a real provider call,
#              capping spend at REPLAY_REAL_LLM_BUDGET_USD per run.
REPLAY_MODE_STUB = "stub"
REPLAY_MODE_REAL_LLM = "real_llm"
REPLAY_MODE_MOCKED_TOOL = "mocked_tool"
REPLAY_MODE_FROZEN_RAG = "frozen_rag"
REPLAY_MODE_LIVE_SANDBOX = "sandbox"
REPLAY_MODE_SHADOW = "shadow"
CANONICAL_REPLAY_MODES = frozenset({
    REPLAY_MODE_STUB,
    REPLAY_MODE_REAL_LLM,
    REPLAY_MODE_MOCKED_TOOL,
    REPLAY_MODE_FROZEN_RAG,
    REPLAY_MODE_LIVE_SANDBOX,
    REPLAY_MODE_SHADOW,
})
REPLAY_MODE_ALIASES = {
    "mocked-tool": REPLAY_MODE_MOCKED_TOOL,
    "live-sandbox": REPLAY_MODE_LIVE_SANDBOX,
}
VALID_REPLAY_MODES = CANONICAL_REPLAY_MODES | frozenset(REPLAY_MODE_ALIASES)
REAL_COMPARISON_REPLAY_MODES = frozenset({
    REPLAY_MODE_REAL_LLM,
    REPLAY_MODE_MOCKED_TOOL,
    REPLAY_MODE_FROZEN_RAG,
    REPLAY_MODE_LIVE_SANDBOX,
    REPLAY_MODE_SHADOW,
})

# Truncation for the stored prompt override — large prompts blow up
# summary_json and the dashboard payload. Anything legitimate fits well
# under 4 KB; rejecting longer ones avoids accidental dumps of huge
# system prompts that would also break LLM context limits anyway.
_MAX_PROMPT_OVERRIDE_CHARS: int = 4000

# Human-readable warning text stamped onto stub-mode runs.
_STUB_MODE_WARNING = (
    "Stub-mode replay: the executor re-graded the originally recorded "
    "response, NOT a re-execution against your current prompt/model. "
    "Prompt edits, model swaps, and RAG-config changes will NOT be "
    "reflected in these results. Enable REPLAY_REAL_LLM_ENABLED on the "
    "control plane (Option B) to detect those regressions."
)

_MODE_WARNINGS = {
    REPLAY_MODE_STUB: _STUB_MODE_WARNING,
    REPLAY_MODE_MOCKED_TOOL: (
        "Mocked-tool replay uses a live model comparison with frozen recorded "
        "tool context where captured tool data is available. Missing tool "
        "snapshots are reported in the tool behavior diff instead of being "
        "treated as verified."
    ),
    REPLAY_MODE_FROZEN_RAG: (
        "Frozen-RAG replay uses the captured retrieved documents as the only "
        "grounding context. Missing retrieval evidence is reported as "
        "not_verified instead of being treated as a pass."
    ),
    REPLAY_MODE_LIVE_SANDBOX: (
        "Live-sandbox replay uses the live model path. Tool execution is "
        "limited to sandbox-capable captured context; unavailable tool calls "
        "are surfaced as warnings, not silently verified."
    ),
    REPLAY_MODE_SHADOW: (
        "Shadow replay compares the candidate configuration side-by-side with "
        "the baseline golden trace. Stub results are never marked verified."
    ),
}


def normalize_replay_mode(replay_mode: str | None) -> str:
    """Return canonical replay mode while accepting legacy wire aliases."""
    mode = (replay_mode or "").strip() or REPLAY_MODE_STUB
    return REPLAY_MODE_ALIASES.get(mode, mode)


# ── dispatch ─────────────────────────────────────────────────────────────────


# ── idempotency horizon (Module 9) ───────────────────────────────────────────
#
# When the GitHub Action retries on transient network errors, or when the
# same workflow re-runs (e.g. CI is re-triggered manually), the dispatch
# endpoint receives the SAME (project_id, golden_set_id, git_sha) tuple
# and must NOT create a second pending run. We dedup by:
#
#   * Any non-terminal run for the tuple ALWAYS wins (regardless of age) —
#     a still-running replay is the live answer to "what's the status of
#     this commit's grade?".
#   * For terminal runs (pass / fail / error), we only return the existing
#     row if it completed within IDEMPOTENCY_TERMINAL_HORIZON_MINUTES.
#     Older terminal runs are considered "stale" and a fresh dispatch
#     creates a new row — useful when a customer re-runs the same commit
#     after fixing a flaky judge or upgrading the model.
#
# Manual triggers (git_sha=None) are NEVER deduped — a human pressing the
# button twice means they want two runs.
IDEMPOTENCY_TERMINAL_HORIZON_MINUTES: int = 60

_TERMINAL_RUN_STATUSES = frozenset({"pass", "warn", "fail", "not_verified", "error"})
_NON_TERMINAL_RUN_STATUSES = frozenset({"pending", "running"})


def _find_idempotent_run(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    git_sha: str,
) -> ReplayRun | None:
    """Return an existing run matching (project, set, sha) per the
    horizon rules in `IDEMPOTENCY_TERMINAL_HORIZON_MINUTES`.

    Searches non-terminal first (no time bound), then terminal within
    the horizon. Caller is responsible for trimming the trailing/leading
    whitespace on `git_sha`; an empty string short-circuits to None.
    """
    if not git_sha:
        return None

    # 1) Any non-terminal run wins regardless of age.
    non_terminal = db.execute(
        select(ReplayRun)
        .where(
            ReplayRun.project_id == project_id,
            ReplayRun.golden_set_id == golden_set_id,
            ReplayRun.git_sha == git_sha,
            ReplayRun.status.in_(_NON_TERMINAL_RUN_STATUSES),
        )
        .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if non_terminal is not None:
        return non_terminal

    # 2) Terminal within horizon.
    horizon_start = datetime.now(timezone.utc) - timedelta(
        minutes=IDEMPOTENCY_TERMINAL_HORIZON_MINUTES
    )
    return db.execute(
        select(ReplayRun)
        .where(
            ReplayRun.project_id == project_id,
            ReplayRun.golden_set_id == golden_set_id,
            ReplayRun.git_sha == git_sha,
            ReplayRun.status.in_(_TERMINAL_RUN_STATUSES),
            # `completed_at` may be NULL on rows that finalized via the
            # error short-circuit before completed_at was set; fall back
            # to created_at in that case.
            (
                (ReplayRun.completed_at.is_not(None) & (ReplayRun.completed_at >= horizon_start))
                | (ReplayRun.completed_at.is_(None) & (ReplayRun.created_at >= horizon_start))
            ),
        )
        .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _resolve_replay_mode(
    *,
    replay_mode: str | None = None,
    candidate_prompt_override: str | None,
    candidate_model_override: str | None,
) -> tuple[str, str | None]:
    """Resolve `replay_mode` from caller intent + global flag.

    Decision table:

        overrides_provided | REPLAY_REAL_LLM_ENABLED | result
        -------------------|--------------------------|-----------------------
        no                 | (any)                    | stub        (default)
        yes                | False                    | ValueError  (reject)
        yes                | True                     | real_llm

    Returns a (mode, warning) tuple. `warning` is a human-readable string
    for stub-mode runs (so the dashboard/API client can show a banner)
    and None for real-LLM runs. Raises ValueError when overrides are
    provided but the global flag is off — this is the *honesty fix*:
    rather than silently dropping the override and running a stub-mode
    replay that ignores the edit, we refuse to dispatch.
    """
    requested_mode = normalize_replay_mode(replay_mode) if replay_mode is not None else None
    if requested_mode is not None and requested_mode not in VALID_REPLAY_MODES:
        raise ValueError(
            "replay_mode must be one of "
            f"{sorted(VALID_REPLAY_MODES)}, got {requested_mode!r}"
        )

    has_override = bool(
        (candidate_prompt_override and candidate_prompt_override.strip())
        or (candidate_model_override and candidate_model_override.strip())
    )

    # Local import: settings is cheap to re-resolve and avoids creating
    # an import-time cycle with config (which itself stays lean).
    from app.core.config import get_settings

    settings = get_settings()
    real_llm_enabled = bool(settings.REPLAY_REAL_LLM_ENABLED)

    if requested_mode is None:
        if not has_override:
            return REPLAY_MODE_STUB, _STUB_MODE_WARNING
        requested_mode = REPLAY_MODE_REAL_LLM

    requested_mode = normalize_replay_mode(requested_mode)

    if requested_mode == REPLAY_MODE_STUB:
        return REPLAY_MODE_STUB, _STUB_MODE_WARNING

    if not real_llm_enabled:
        raise ValueError(
            f"replay_mode={requested_mode!r} requires real comparison replay, "
            "but REPLAY_REAL_LLM_ENABLED is False on the control plane. "
            "Enable it or use replay_mode='stub' for a sanity check."
        )

    return requested_mode, _MODE_WARNINGS.get(requested_mode)


def dispatch_replay_run(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    trigger: str = "manual",
    git_sha: str | None = None,
    branch_name: str | None = None,
    pr_number: int | None = None,
    commit_message: str | None = None,
    replay_mode: str | None = None,
    candidate_prompt_override: str | None = None,
    candidate_model_override: str | None = None,
) -> ReplayRun | None:
    """Create a pending ReplayRun for the given golden set.

    Returns the new run, the existing run when an idempotent match is
    found (Module 9), or None if the golden set does not exist for this
    project. Raises ValueError on invalid trigger or on candidate
    overrides supplied without `Settings.REPLAY_REAL_LLM_ENABLED`.

    The run starts in `pending` status with summary_json holding the
    snapshot of `trace_count_at_dispatch` so the dashboard can render
    progress accurately even if the underlying golden set changes mid-run.

    Module 9 additions:
      * Idempotency on `(project_id, golden_set_id, git_sha)` per the
        horizon rules in `IDEMPOTENCY_TERMINAL_HORIZON_MINUTES`. Manual
        runs (git_sha=None) are never deduped. See `_find_idempotent_run`.
      * Optional `branch_name`, `pr_number`, `commit_message` are stored
        in `summary_json` for dashboard display. None of these are
        promoted to columns because the cardinality is tied to git_sha
        and they're free-text / display-only — adding columns just to
        index them is unnecessary.

    Option A (honesty fix) additions:
      * ``candidate_prompt_override`` — replacement prompt to apply at
        re-execution time. Requires real-LLM mode; otherwise raises.
      * ``candidate_model_override`` — replacement model slug. Same gating.
      * ``summary_json["replay_mode"]`` is always stamped ("stub" or
        "real_llm") so the dashboard can render an accurate banner.
      * ``summary_json["replay_mode_warning"]`` is stamped on stub-mode
        runs explaining the limitation (no real LLM call).
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(
            f"trigger must be one of {sorted(VALID_TRIGGERS)}, got {trigger!r}"
        )

    # Resolve replay_mode + validate override gating BEFORE any DB work.
    # This raises on misconfigured override → real-LLM-off so we never
    # write a misleading pending row.
    replay_mode, replay_mode_warning = _resolve_replay_mode(
        replay_mode=replay_mode,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
    )
    requested_replay_mode = replay_mode
    executor_replay_mode = (
        REPLAY_MODE_REAL_LLM
        if replay_mode in REAL_COMPARISON_REPLAY_MODES
        else replay_mode
    )

    # Truncate the stored prompt — see _MAX_PROMPT_OVERRIDE_CHARS rationale.
    normalized_prompt_override: str | None = None
    if candidate_prompt_override and candidate_prompt_override.strip():
        normalized_prompt_override = candidate_prompt_override[
            :_MAX_PROMPT_OVERRIDE_CHARS
        ]
    normalized_model_override: str | None = None
    if candidate_model_override and candidate_model_override.strip():
        normalized_model_override = candidate_model_override.strip()

    parent = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if parent is None:
        return None

    # Idempotency check — only when sha is provided. Manual button
    # presses (git_sha=None) skip this and always create a new row so a
    # human pressing twice gets the second run they asked for.
    #
    # Overrides also bypass idempotency: each (prompt, model) pair is a
    # distinct experiment even on the same git_sha, so deduping would
    # silently return a run that tested a DIFFERENT candidate. Force a
    # fresh row in that case.
    normalized_sha = (git_sha or "").strip() or None
    has_override = (
        normalized_prompt_override is not None
        or normalized_model_override is not None
        or requested_replay_mode in REAL_COMPARISON_REPLAY_MODES
    )
    if normalized_sha is not None and not has_override:
        existing = _find_idempotent_run(
            db,
            project_id=project_id,
            golden_set_id=golden_set_id,
            git_sha=normalized_sha,
        )
        if existing is not None:
            logger.info(
                "replay_run_idempotent_hit project=%s run=%s set=%s sha=%s status=%s",
                project_id,
                existing.id,
                golden_set_id,
                normalized_sha,
                existing.status,
            )
            # Module 9: stamp a transient attribute the routes use to
            # populate `idempotent: True` in their response without
            # changing the function's return type. SQLAlchemy permits
            # ad-hoc instance attributes that don't shadow mapped
            # columns; this one starts with `_zroky_` to make the
            # convention obvious.
            existing._zroky_was_new = False  # type: ignore[attr-defined]
            return existing

    snapshot_count = count_traces(
        db,
        project_id=project_id,
        golden_set_id=golden_set_id,
        status=GOLDEN_TRACE_STATUS_ACTIVE,
    )
    summary: dict[str, Any] = {
        "trace_count_at_dispatch": snapshot_count,
        "pass_count": 0,
        "fail_count": 0,
        "error_count": 0,
        # Option A honesty fields — ALWAYS present so frontends can
        # render the right banner without conditional null-checks.
        "replay_mode": executor_replay_mode,
        "requested_replay_mode": requested_replay_mode,
        "verification_status": "sanity_check_only"
        if requested_replay_mode == REPLAY_MODE_STUB
        else "pending_real_comparison",
        "verified_fix": False,
    }
    if replay_mode_warning:
        summary["replay_mode_warning"] = replay_mode_warning
    if normalized_prompt_override is not None:
        summary["candidate_prompt_override"] = normalized_prompt_override
    if normalized_model_override is not None:
        summary["candidate_model_override"] = normalized_model_override
    # Module 9: stash CI-context metadata into summary_json. Only persist
    # truthy values to avoid bloating the row with None placeholders.
    if branch_name:
        summary["branch_name"] = str(branch_name)[:255]
    if pr_number is not None:
        try:
            summary["pr_number"] = int(pr_number)
        except (TypeError, ValueError):
            pass  # silently drop unusable values
    if commit_message:
        # Single-line preview; full message is recoverable from the
        # commit itself if anyone needs it.
        first_line = str(commit_message).splitlines()[0] if commit_message else ""
        summary["commit_message"] = first_line[:200]

    now = datetime.now(timezone.utc)
    run = ReplayRun(
        id=str(uuid4()),
        project_id=project_id,
        golden_set_id=golden_set_id,
        trigger=trigger,
        git_sha=normalized_sha,
        status="pending",
        summary_json=json.dumps(summary, separators=(",", ":")),
        created_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run._zroky_was_new = True  # type: ignore[attr-defined]
    logger.info(
        "replay_run_dispatched project=%s run=%s set=%s trigger=%s traces=%d",
        project_id,
        run.id,
        golden_set_id,
        trigger,
        snapshot_count,
    )
    return run


def was_idempotent_hit(run: ReplayRun) -> bool:
    """Return True iff `run` was returned from an idempotency match
    (vs. a freshly inserted row) on the most recent
    `dispatch_replay_run` call. Defaults to False if the attribute is
    missing — i.e. the run came from somewhere other than the dispatch
    service.
    """
    return getattr(run, "_zroky_was_new", True) is False


def create_replay_from_call(
    db: Session,
    *,
    project_id: str,
    call_id: str,
    replay_mode: str = REPLAY_MODE_STUB,
    candidate_prompt_override: str | None = None,
    candidate_model_override: str | None = None,
) -> ReplayRun | None:
    call = db.execute(
        select(Call).where(Call.project_id == project_id, Call.id == call_id)
    ).scalar_one_or_none()
    if call is None:
        return None
    _resolve_replay_mode(
        replay_mode=replay_mode,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
    )

    golden_set = create_golden_set(
        db,
        project_id=project_id,
        name=_one_click_set_name(source_kind="call", source_id=call_id),
        description=f"Auto-created from call {call_id}.",
    )
    source_output_text, _ = source_evidence_from_call(call)
    trace = mark_call_as_golden(
        db,
        project_id=project_id,
        call_id=call_id,
        golden_set_id=golden_set.id,
        expected_output_text=source_output_text,
    )
    if trace is None:
        return None

    run = dispatch_replay_run(
        db,
        project_id=project_id,
        golden_set_id=golden_set.id,
        trigger="manual",
        replay_mode=replay_mode,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
    )
    if run is None:
        return None

    summary = parse_summary(run.summary_json)
    summary["source_kind"] = "call"
    summary["source_id"] = call_id
    summary["source_call_id"] = call_id
    summary["source_context"] = _source_context_from_call(call)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_replay_from_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    replay_mode: str = REPLAY_MODE_STUB,
    candidate_prompt_override: str | None = None,
    candidate_model_override: str | None = None,
) -> ReplayRun | None:
    anomaly = db.execute(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.id == issue_id)
    ).scalar_one_or_none()
    if anomaly is None:
        return None
    issue = issue_projection_from_anomaly(anomaly)
    if not issue.sample_call_id:
        raise ValueError("Issue has no sample_call_id to replay.")

    run = create_replay_from_call(
        db,
        project_id=project_id,
        call_id=issue.sample_call_id,
        replay_mode=replay_mode,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
    )
    if run is None:
        return None

    summary = parse_summary(run.summary_json)
    summary["source_kind"] = "issue"
    summary["source_id"] = issue_id
    summary["source_issue_id"] = issue_id
    summary["source_issue_failure_code"] = issue.failure_code
    summary["source_issue_severity"] = issue.severity
    summary["source_context"] = _source_context_from_issue(anomaly)
    run.summary_json = json.dumps(summary, separators=(",", ":"))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ── reads ────────────────────────────────────────────────────────────────────


def get_replay_run(
    db: Session, *, project_id: str, run_id: str
) -> ReplayRun | None:
    return db.execute(
        select(ReplayRun).where(
            ReplayRun.project_id == project_id,
            ReplayRun.id == run_id,
        )
    ).scalar_one_or_none()


def list_replay_runs(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
    before_created_at: datetime | None = None,
    before_id: str | None = None,
) -> list[ReplayRun]:
    """List replay runs for a project, newest-first by created_at.

    Optional filters: `golden_set_id`, `status`. Stable cursor is
    `(created_at, id)` strict-less-than tuple.
    """
    conditions = [ReplayRun.project_id == project_id]
    if golden_set_id is not None:
        conditions.append(ReplayRun.golden_set_id == golden_set_id)
    if status is not None:
        if status not in VALID_RUN_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_RUN_STATUSES)}, got {status!r}"
            )
        conditions.append(ReplayRun.status == status)
    if before_created_at is not None and before_id is not None:
        conditions.append(
            or_(
                ReplayRun.created_at < before_created_at,
                and_(
                    ReplayRun.created_at == before_created_at,
                    ReplayRun.id < before_id,
                ),
            )
        )

    rows = db.execute(
        select(ReplayRun)
        .where(*conditions)
        .order_by(ReplayRun.created_at.desc(), ReplayRun.id.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


def list_run_traces(
    db: Session, *, project_id: str, run_id: str
) -> list[ReplayRunTrace] | None:
    """Return the per-trace verdicts for one run, or None if the run does
    not exist for this project (so the route can 404 cleanly)."""
    parent = get_replay_run(db, project_id=project_id, run_id=run_id)
    if parent is None:
        return None
    rows = db.execute(
        select(ReplayRunTrace)
        .where(
            ReplayRunTrace.project_id == project_id,
            ReplayRunTrace.replay_run_id == run_id,
        )
        .order_by(ReplayRunTrace.created_at.asc(), ReplayRunTrace.id.asc())
    ).scalars().all()
    return list(rows)


# ── mark-as-golden convenience ───────────────────────────────────────────────


def mark_call_as_golden(
    db: Session,
    *,
    project_id: str,
    call_id: str,
    golden_set_id: str,
    weight: float = 1.0,
    status: str | None = None,
    expected_output_text: str | None = None,
    criteria_json: str | None = None,
) -> GoldenTrace | None:
    """Snapshot a Call's tokens/cost/latency and add it as a GoldenTrace.

    Returns:
      - GoldenTrace on success
      - None if the call does not exist for this tenant
      - None if the golden set does not exist for this tenant
      - Raises ValueError on invalid weight or missing tenancy match
    """
    call = db.execute(
        select(Call).where(Call.id == call_id, Call.project_id == project_id)
    ).scalar_one_or_none()
    if call is None:
        return None

    parent = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if parent is None:
        return None

    expected_cost_usd = (
        float(call.cost_total) if call.cost_total is not None else None
    )
    expected_tokens = int(call.total_tokens) if call.total_tokens else None
    expected_latency_ms = (
        int(call.latency_ms) if call.latency_ms is not None else None
    )
    source_output_text, source_evidence_json = source_evidence_from_call(call)

    return add_trace(
        db,
        project_id=project_id,
        golden_set_id=golden_set_id,
        call_id=call_id,
        status=status,
        expected_output_text=expected_output_text,
        source_output_text=source_output_text,
        source_evidence_json=source_evidence_json,
        expected_tokens=expected_tokens,
        expected_cost_usd=expected_cost_usd,
        expected_latency_ms=expected_latency_ms,
        criteria_json=criteria_json,
        weight=weight,
    )
