"""
Pilot Tier-2 PR payload generator (ZROKY-TECHNICAL-PLAN-V2 §6.3 / §6.4 / Module 10).

Pure-functional surface that converts an `Anomaly` row + the diagnose
engine's evidence into a `PRPayload` — the title, body, target branch,
and minimal patch the autopilot would propose to the customer's repo.

This module does NOT touch the network. It does NOT decide whether to
actually open the PR (that's the policy layer in `pilot_pr_dispatch`).
Its only job is to produce a deterministic, fingerprinted payload so:

  1. The same anomaly + diagnose evidence always yields the same
     fingerprint — driving idempotency in the dispatcher.
  2. Tests can assert on shape without mocking HTTP.
  3. Future swaps to GitHub App (vs. OAuth, plan §17.3 #2) require
     ZERO changes here — only the `GitHubPRClient` impl that consumes
     this payload changes.

Supported `action_type` values (subset of `pilot_policies.tier2_actions`):

  * `prompt_revert_pr`   — revert the system prompt to the last known
                           good revision; patch is a single-file edit
                           to the agent's prompt asset.
  * `schema_fix_pr`      — propose a JSON-Schema tightening when the
                           detector found `SCHEMA_VIOLATION`. Patch
                           edits the schema file path indicated by the
                           anomaly evidence.

Unsupported action types raise `UnsupportedActionTypeError` rather
than silently producing a no-op patch — keeping the contract tight
(plan §17.1 risk #1: false-positive auto-revert is the top risk).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from app.db.models import Anomaly

logger = logging.getLogger(__name__)


# ── vocab ────────────────────────────────────────────────────────────────────

# Mirrors `services.pilot.DEFAULT_POLICY["tier2_actions"]`. Kept in
# sync manually — both sides import-test it via the cross-check
# helper at the bottom of this file (`_check_action_vocab_in_sync`).
SUPPORTED_TIER2_ACTIONS: frozenset[str] = frozenset({
    "prompt_revert_pr",
    "schema_fix_pr",
    # Replay-driven auto-fix actions (most advanced — Enterprise only)
    "replay_prompt_fix",
    "replay_model_fix",
})

# Conservative defaults — overridable per-project via policy_json
# extensions in a later module. For now hardcoded because the plan
# §6.3 schema does not yet expose a branch field.
DEFAULT_BASE_BRANCH: str = "main"
DEFAULT_BRANCH_PREFIX: str = "zroky/autopilot"


class UnsupportedActionTypeError(ValueError):
    """Raised when the dispatcher asks for an action_type not in
    `SUPPORTED_TIER2_ACTIONS`. Caller should record the action with
    status='skipped' rather than retrying."""


class InsufficientEvidenceError(ValueError):
    """Raised when the anomaly does not carry enough evidence to
    construct a meaningful patch — e.g. a `schema_fix_pr` request
    against an anomaly with no detected schema path. Caller maps this
    to status='skipped'; the worker should NOT retry."""


# ── patch file model ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatchFile:
    """One file's worth of changes.

    `path` is repo-relative (e.g. `prompts/agent.txt`). `new_content`
    is the full new contents — Tier-2 patches are intentionally tiny
    (single-file, full-replace) to keep the human review cost low.
    The `GitHubPRClient` implementation translates this into a blob
    create + tree update + commit on the chosen branch.

    `old_content_fingerprint` is optional. If supplied, the client
    verifies the current HEAD of `path` matches the fingerprint
    before writing — preventing a stale patch from clobbering a
    human edit made between dispatch and apply. NULL skips the
    check (used when the action is a from-scratch schema fix).
    """

    path: str
    new_content: str
    old_content_fingerprint: str | None = None


@dataclass(frozen=True)
class PRPayload:
    """The full proposal handed to the `GitHubPRClient`.

    Frozen + JSON-serializable so it can be persisted into
    `pilot_actions.payload_json` and replayed on retry without
    re-running the generator.
    """

    project_id: str
    anomaly_id: str
    action_type: str
    title: str
    body: str
    base_branch: str
    head_branch: str
    files: tuple[PatchFile, ...]
    # Fingerprint over (project_id, anomaly_id, action_type, files).
    # Distinct from `replay_run_id_gate` (which is the *gate*
    # evidence) — this is the *patch* identity.
    fingerprint: str
    # Verbatim copy of the diagnose evidence that motivated the
    # patch. Embedded in the PR body so reviewers can audit the
    # decision; also stashed here for the audit trail.
    evidence_summary: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize for `pilot_actions.payload_json`. Stable key
        ordering so identical payloads produce byte-identical
        strings (helps log diffing + idempotency cross-checks)."""
        return json.dumps(
            {
                **asdict(self),
                "files": [asdict(f) for f in self.files],
            },
            separators=(",", ":"),
            sort_keys=True,
        )


# ── public API ───────────────────────────────────────────────────────────────


def build_pr_payload(
    *,
    anomaly: Anomaly,
    action_type: str,
    base_branch: str | None = None,
    branch_prefix: str | None = None,
) -> PRPayload:
    """Construct a `PRPayload` from an Anomaly + diagnose evidence.

    Reads `anomaly.evidence_json` to extract the candidate change that
    motivated the patch. Raises `InsufficientEvidenceError` if the
    evidence is missing or malformed for the requested action_type.
    Raises `UnsupportedActionTypeError` if the action_type is not in
    `SUPPORTED_TIER2_ACTIONS`.

    `base_branch` defaults to `DEFAULT_BASE_BRANCH`. `branch_prefix`
    defaults to `DEFAULT_BRANCH_PREFIX`; the head branch is
    `{prefix}/anomaly-{anomaly.id[:12]}` so the same anomaly always
    targets the same branch and a retry updates the existing PR
    rather than opening a new one.
    """
    if action_type not in SUPPORTED_TIER2_ACTIONS:
        raise UnsupportedActionTypeError(
            f"action_type {action_type!r} is not a supported tier-2 action "
            f"(supported: {sorted(SUPPORTED_TIER2_ACTIONS)})"
        )

    evidence = _parse_evidence(anomaly.evidence_json)

    if action_type == "prompt_revert_pr":
        patch_file, summary = _build_prompt_revert_patch(anomaly, evidence)
    elif action_type == "schema_fix_pr":
        patch_file, summary = _build_schema_fix_patch(anomaly, evidence)
    elif action_type == "replay_prompt_fix":
        patch_file, summary = _build_replay_prompt_fix_patch(anomaly, evidence)
    elif action_type == "replay_model_fix":
        patch_file, summary = _build_replay_model_fix_patch(anomaly, evidence)
    else:  # pragma: no cover — the vocab check above is exhaustive
        raise UnsupportedActionTypeError(action_type)

    files = (patch_file,)
    base = (base_branch or DEFAULT_BASE_BRANCH).strip() or DEFAULT_BASE_BRANCH
    prefix = (branch_prefix or DEFAULT_BRANCH_PREFIX).strip() or DEFAULT_BRANCH_PREFIX
    # Branch name is anomaly-scoped (not patch-scoped) so retries
    # land on the same branch; the GitHubPRClient takes care of
    # force-updating the head ref if the patch changed.
    head_branch = f"{prefix}/anomaly-{anomaly.id[:12]}"

    title = _build_title(anomaly, action_type, summary)
    body = _build_body(anomaly, action_type, summary, evidence)

    fingerprint = compute_pr_fingerprint(
        project_id=anomaly.project_id,
        anomaly_id=anomaly.id,
        action_type=action_type,
        files=files,
    )

    return PRPayload(
        project_id=anomaly.project_id,
        anomaly_id=anomaly.id,
        action_type=action_type,
        title=title,
        body=body,
        base_branch=base,
        head_branch=head_branch,
        files=files,
        fingerprint=fingerprint,
        evidence_summary=summary,
    )


def compute_pr_fingerprint(
    *,
    project_id: str,
    anomaly_id: str,
    action_type: str,
    files: tuple[PatchFile, ...],
) -> str:
    """SHA-256 hex digest over the parts of the payload that define
    "this is the same patch".

    Title + body are intentionally excluded — humans tweaking the PR
    body should not invalidate idempotency. Branch names are excluded
    because the head_branch is derived from anomaly_id and is therefore
    already covered.

    Order: project_id → anomaly_id → action_type → each file's
    (path, new_content, old_content_fingerprint) tuple, JSON-serialized
    with sorted keys for cross-platform stability.
    """
    payload = {
        "project_id": project_id,
        "anomaly_id": anomaly_id,
        "action_type": action_type,
        "files": [
            {
                "path": f.path,
                "new_content": f.new_content,
                "old_content_fingerprint": f.old_content_fingerprint,
            }
            for f in files
        ],
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ── internals ────────────────────────────────────────────────────────────────


def _parse_evidence(evidence_json: str | None) -> dict[str, Any]:
    """Defensive parser for `anomalies.evidence_json`. Returns an
    empty dict on missing / invalid JSON so the per-action builders
    can fail with a clean `InsufficientEvidenceError` message."""
    if not evidence_json:
        return {}
    try:
        decoded = json.loads(evidence_json)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _build_prompt_revert_patch(
    anomaly: Anomaly, evidence: dict[str, Any]
) -> tuple[PatchFile, dict[str, Any]]:
    """Construct the single-file patch for `prompt_revert_pr`.

    Expects `evidence` to carry:
        * `prompt_path`         repo-relative path to the prompt asset
        * `prior_prompt_body`   the previous-known-good prompt text
        * `current_prompt_fingerprint` (optional) SHA of current text

    The current-content fingerprint is forwarded so the
    `GitHubPRClient` can detect a stale patch (someone edited the
    prompt after Zroky's diagnose ran).
    """
    prompt_path = _require_str_field(evidence, "prompt_path")
    prior_body = _require_str_field(evidence, "prior_prompt_body")
    current_fp = evidence.get("current_prompt_fingerprint")
    if current_fp is not None and not isinstance(current_fp, str):
        current_fp = None

    summary = {
        "kind": "prompt_revert",
        "prompt_path": prompt_path,
        "current_prompt_fingerprint": current_fp,
        "prior_prompt_length": len(prior_body),
    }
    return (
        PatchFile(
            path=prompt_path,
            new_content=prior_body,
            old_content_fingerprint=current_fp,
        ),
        summary,
    )


def _build_schema_fix_patch(
    anomaly: Anomaly, evidence: dict[str, Any]
) -> tuple[PatchFile, dict[str, Any]]:
    """Construct the single-file patch for `schema_fix_pr`.

    Expects `evidence` to carry:
        * `schema_path`           repo-relative path to the schema file
        * `proposed_schema_body`  full new schema text (json string)
        * `current_schema_fingerprint` (optional)
    """
    schema_path = _require_str_field(evidence, "schema_path")
    proposed_body = _require_str_field(evidence, "proposed_schema_body")
    current_fp = evidence.get("current_schema_fingerprint")
    if current_fp is not None and not isinstance(current_fp, str):
        current_fp = None

    summary = {
        "kind": "schema_fix",
        "schema_path": schema_path,
        "current_schema_fingerprint": current_fp,
        "proposed_schema_length": len(proposed_body),
    }
    return (
        PatchFile(
            path=schema_path,
            new_content=proposed_body,
            old_content_fingerprint=current_fp,
        ),
        summary,
    )


def _require_str_field(evidence: dict[str, Any], key: str) -> str:
    value = evidence.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InsufficientEvidenceError(
            f"evidence is missing required string field {key!r}"
        )
    return value


def _build_replay_prompt_fix_patch(
    anomaly: Anomaly, evidence: dict[str, Any]
) -> tuple[PatchFile, dict[str, Any]]:
    """Construct patch for replay_prompt_fix — LLM-generated prompt tweak.

    Expects `evidence` to carry:
        * `prompt_path`         repo-relative path to the prompt asset
        * `proposed_prompt_body` the new prompt text (tweaked by engine)
        * `current_prompt_fingerprint` (optional) SHA of current text
        * `regression_summary`  human-readable description of what broke
    """
    prompt_path = _require_str_field(evidence, "prompt_path")
    proposed_body = _require_str_field(evidence, "proposed_prompt_body")
    current_fp = evidence.get("current_prompt_fingerprint")
    if current_fp is not None and not isinstance(current_fp, str):
        current_fp = None

    summary = {
        "kind": "replay_prompt_fix",
        "prompt_path": prompt_path,
        "current_prompt_fingerprint": current_fp,
        "proposed_prompt_length": len(proposed_body),
        "regression_summary": evidence.get("regression_summary", ""),
    }
    return (
        PatchFile(
            path=prompt_path,
            new_content=proposed_body,
            old_content_fingerprint=current_fp,
        ),
        summary,
    )


def _build_replay_model_fix_patch(
    anomaly: Anomaly, evidence: dict[str, Any]
) -> tuple[PatchFile, dict[str, Any]]:
    """Construct patch for replay_model_fix — swap model in config.

    Expects `evidence` to carry:
        * `config_path`         repo-relative path to model config
        * `proposed_model`      new model slug (e.g. "gpt-4o")
        * `current_model`       current model slug
        * `regression_summary`  human-readable description of what broke
    """
    config_path = _require_str_field(evidence, "config_path")
    proposed_model = _require_str_field(evidence, "proposed_model")
    current_model = evidence.get("current_model", "")
    summary = {
        "kind": "replay_model_fix",
        "config_path": config_path,
        "current_model": current_model,
        "proposed_model": proposed_model,
        "regression_summary": evidence.get("regression_summary", ""),
    }
    # Patch is a JSON/YAML snippet that replaces the model field.
    # The exact shape depends on the customer's config format; we
    # emit a simple key-value replacement that the human reviewer
    # can adapt.
    patch_body = (
        f"# Auto-generated model swap by Zroky replay fix engine\n"
        f"# Regression: {summary['regression_summary']}\n"
        f"# Replace model reference below:\n"
        f"model: {proposed_model}\n"
    )
    return (
        PatchFile(
            path=config_path,
            new_content=patch_body,
            old_content_fingerprint=None,
        ),
        summary,
    )


def _build_title(
    anomaly: Anomaly, action_type: str, summary: dict[str, Any]
) -> str:
    """Title is single-line, ≤ 80 chars after the prefix, and includes
    the anomaly fingerprint short hash so two PRs for distinct anomalies
    are visually distinguishable in a busy queue."""
    short_fp = (anomaly.fingerprint or "")[:8] or "unknown"
    if action_type == "prompt_revert_pr":
        suffix = f"revert prompt {summary.get('prompt_path', '')}"
    elif action_type == "schema_fix_pr":
        suffix = f"tighten schema {summary.get('schema_path', '')}"
    elif action_type == "replay_prompt_fix":
        suffix = f"fix prompt {summary.get('prompt_path', '')}"
    elif action_type == "replay_model_fix":
        suffix = f"swap model → {summary.get('proposed_model', '')}"
    else:  # pragma: no cover — defended above
        suffix = action_type
    full = f"[zroky] {suffix} (anomaly {short_fp})"
    return full[:200]  # GitHub allows 256; cap further for sanity


def _build_body(
    anomaly: Anomaly,
    action_type: str,
    summary: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    """Multi-line markdown body the customer's reviewer sees in the PR.

    Intentionally factual — no marketing copy, no first-person voice.
    The reviewer is on call at 3am; they want the facts.
    """
    lines: list[str] = []
    lines.append(f"**Anomaly**: `{anomaly.id}`")
    lines.append(f"**Detector**: `{anomaly.detector}`")
    lines.append(f"**Severity**: `{anomaly.severity}`")
    lines.append(f"**Occurrences**: `{anomaly.occurrence_count}`")
    lines.append("")
    lines.append("## Proposed change")
    if action_type == "prompt_revert_pr":
        lines.append(
            f"Revert `{summary['prompt_path']}` to the last known good "
            f"revision ({summary['prior_prompt_length']} chars)."
        )
    elif action_type == "schema_fix_pr":
        lines.append(
            f"Replace `{summary['schema_path']}` with the proposed "
            f"schema ({summary['proposed_schema_length']} chars)."
        )
    elif action_type == "replay_prompt_fix":
        lines.append(
            f"Update `{summary['prompt_path']}` with a targeted fix "
            f"({summary['proposed_prompt_length']} chars)."
        )
        reg_summary = summary.get("regression_summary", "")
        if reg_summary:
            lines.append("")
            lines.append(f"**Regression**: {reg_summary}")
    elif action_type == "replay_model_fix":
        lines.append(
            f"Swap model in `{summary['config_path']}` from "
            f"`{summary['current_model']}` → `{summary['proposed_model']}`."
        )
        reg_summary = summary.get("regression_summary", "")
        if reg_summary:
            lines.append("")
            lines.append(f"**Regression**: {reg_summary}")
    lines.append("")
    lines.append("## Why Zroky proposed this")
    if action_type in {"replay_prompt_fix", "replay_model_fix"}:
        lines.append(
            "This PR was generated by Zroky's replay-driven auto-fix engine. "
            "A replay run with your proposed prompt/model change was executed "
            "against the golden set; traces that previously passed now failed. "
            "The fix engine analyzed the failing traces and generated this "
            "targeted patch. Review carefully and merge or close as appropriate."
        )
    else:
        lines.append(
            "This PR was generated by Zroky's Tier-2 autopilot after the "
            "anomaly cleared the replay-pass gate. Review the diff carefully "
            "and merge or close as appropriate. Merging this PR will be "
            "recorded against the anomaly's audit trail."
        )
    candidates = evidence.get("candidates")
    if isinstance(candidates, list) and candidates:
        lines.append("")
        lines.append("## Diagnose evidence (top candidates)")
        for idx, cand in enumerate(candidates[:3], start=1):
            if not isinstance(cand, dict):
                continue
            signal = cand.get("signal", "?")
            confidence = cand.get("confidence", "?")
            lines.append(f"{idx}. `{signal}` — confidence `{confidence}`")
    lines.append("")
    lines.append("---")
    lines.append(
        "_Close this PR without merging if the change is wrong — Zroky "
        "records the decision and will not re-open the same patch._"
    )
    return "\n".join(lines)


# ── vocab cross-check (import-time sanity) ───────────────────────────────────


def _check_action_vocab_in_sync() -> None:
    """Defensive cross-check: the action types accepted here MUST be a
    subset of `pilot_policies.tier2_actions` default. If we ever
    diverge, the dispatch layer would skip every tier-2 evaluation.

    Called from `services.pilot`'s module-load via the test suite — not
    at import time of THIS module to avoid a circular import."""
    from app.services.pilot import DEFAULT_POLICY

    allowed = set(DEFAULT_POLICY.get("tier2_actions", []))
    drift = SUPPORTED_TIER2_ACTIONS - allowed
    if drift:
        raise RuntimeError(
            f"pilot_pr_payload supports action_types {sorted(drift)} that "
            f"are not in pilot.DEFAULT_POLICY[tier2_actions] {sorted(allowed)}"
        )
