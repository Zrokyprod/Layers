from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


OWNER_PROOF_BLOCKER = "real_customer_proof:real_customer_outcome_proof_missing"
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_PROOF_FLAGS = frozenset(
    {
        "captured_call_linked",
        "unsafe_action_stopped",
        "connector_configured",
        "connector_health_verified",
        "real_connector_ready",
        "matched_outcome_shown",
        "evidence_hash_visible",
        "evidence_pack_passed",
        "secrets_redacted",
    }
)


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _https_non_example_url(value: Any) -> bool:
    if not _non_empty_string(value):
        return False
    normalized = value.strip().lower()
    return normalized.startswith("https://") and "example.com" not in normalized


def validate_summary(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    launch_readiness = summary.get("launch_readiness") or {}
    owner_readiness = launch_readiness.get("owner_launch_readiness") or {}
    runtime_policy = summary.get("runtime_policy") or {}
    outcome = summary.get("outcome_reconciliation") or {}
    connector_setup = summary.get("connector_setup") or {}
    evidence_pack = summary.get("evidence_pack") or {}
    proof = summary.get("proof") or {}
    hard_blockers = owner_readiness.get("hard_blockers") or []
    matched_outcomes = _integer(
        owner_readiness.get("real_customer_matched_outcomes_7d")
    )
    connector_http_status = _integer(outcome.get("connector_http_status"))
    evidence_hash = evidence_pack.get("evidence_hash")

    _require(errors, summary.get("mode") == "live", "summary.mode must be live")
    _require(errors, _non_empty_string(summary.get("project_id")), "project_id must be present")
    _require(errors, _non_empty_string(summary.get("scenario")), "scenario must be present")
    _require(errors, _non_empty_string(summary.get("call_id")), "call_id must be present")
    _require(errors, _non_empty_string(summary.get("trace_id")), "trace_id must be present")
    _require(
        errors,
        launch_readiness.get("proof_mode") == "live_customer",
        "launch_readiness.proof_mode must be live_customer",
    )
    _require(
        errors,
        launch_readiness.get("real_customer_proof_candidate") is True,
        "launch_readiness.real_customer_proof_candidate must be true",
    )
    _require(
        errors,
        owner_readiness.get("checked") is True,
        "launch_readiness.owner_launch_readiness.checked must be true",
    )
    _require(
        errors,
        owner_readiness.get("real_customer_proof_status") == "pass",
        "owner real_customer_proof_status must be pass",
    )
    _require(
        errors,
        matched_outcomes is not None and matched_outcomes >= 1,
        "owner real_customer_matched_outcomes_7d must be at least 1",
    )
    _require(
        errors,
        OWNER_PROOF_BLOCKER not in hard_blockers,
        f"owner hard_blockers must not include {OWNER_PROOF_BLOCKER}",
    )
    _require(
        errors,
        runtime_policy.get("allowed") is False,
        "runtime_policy.allowed must be false",
    )
    _require(
        errors,
        _non_empty_string(runtime_policy.get("decision_id")),
        "runtime_policy.decision_id must be present",
    )
    _require(
        errors,
        outcome.get("verdict") == "matched",
        "outcome_reconciliation.verdict must be matched",
    )
    _require(
        errors,
        _https_non_example_url(outcome.get("connector_request_url")),
        "outcome_reconciliation.connector_request_url must be a real https URL, not example.com",
    )
    _require(
        errors,
        connector_http_status is not None and 200 <= connector_http_status <= 299,
        "outcome_reconciliation.connector_http_status must be 2xx",
    )
    _require(
        errors,
        outcome.get("connector_error") in (None, ""),
        "outcome_reconciliation.connector_error must be empty",
    )
    _require(
        errors,
        outcome.get("connector_retryable") in (None, False),
        "outcome_reconciliation.connector_retryable must not be true",
    )
    _require(
        errors,
        _non_empty_string(outcome.get("system_ref")),
        "outcome_reconciliation.system_ref must be present",
    )
    _require(
        errors,
        evidence_pack.get("verification_status") == "pass",
        "evidence_pack.verification_status must be pass",
    )
    _require(
        errors,
        evidence_pack.get("decision_id") == runtime_policy.get("decision_id"),
        "evidence_pack.decision_id must match runtime_policy.decision_id",
    )
    _require(
        errors,
        evidence_pack.get("hash_algorithm") == "sha256",
        "evidence_pack.hash_algorithm must be sha256",
    )
    _require(
        errors,
        (
            isinstance(evidence_hash, str)
            and SHA256_HEX_RE.fullmatch(evidence_hash) is not None
        ),
        "evidence_pack.evidence_hash must be a lowercase sha256 hex digest",
    )
    _require(
        errors,
        (_integer(evidence_pack.get("outcome_count")) or 0) >= 1,
        "evidence_pack.outcome_count must be at least 1",
    )
    _require(
        errors,
        (_integer(evidence_pack.get("audit_event_count")) or 0) >= 1,
        "evidence_pack.audit_event_count must be at least 1",
    )
    _require(
        errors,
        connector_setup.get("connected") is True,
        "connector_setup.connected must be true",
    )
    _require(
        errors,
        connector_setup.get("config_saved") is True,
        "connector_setup.config_saved must be true",
    )
    _require(
        errors,
        connector_setup.get("health_status") == "healthy",
        "connector_setup.health_status must be healthy",
    )
    _require(
        errors,
        connector_setup.get("last_verdict") == "matched",
        "connector_setup.last_verdict must be matched",
    )
    _require(
        errors,
        connector_setup.get("readiness_status") == "ready",
        "connector_setup.readiness_status must be ready",
    )
    _require(
        errors,
        connector_setup.get("secrets_redacted") is True,
        "connector_setup.secrets_redacted must be true",
    )
    _require(errors, bool(proof), "proof object must be present")
    missing_proofs = sorted(EXPECTED_PROOF_FLAGS - set(proof))
    _require(
        errors,
        not missing_proofs,
        "proof object missing required keys: " + ", ".join(missing_proofs),
    )
    false_proofs = sorted(key for key in EXPECTED_PROOF_FLAGS if proof.get(key) is not True)
    _require(
        errors,
        not false_proofs,
        "every proof value must be true; false/missing keys: "
        + ", ".join(false_proofs),
    )

    return errors


def validate_evidence(
    summary: dict[str, Any], evidence: dict[str, Any], evidence_path: Path
) -> list[str]:
    errors: list[str] = []
    summary_pack = summary.get("evidence_pack") or {}
    evidence_outcomes = evidence.get("outcome_reconciliation") or []
    evidence_call = evidence.get("call") or {}
    matched_outcomes = [
        outcome
        for outcome in evidence_outcomes
        if isinstance(outcome, dict) and outcome.get("verdict") == "matched"
    ]

    _require(
        errors,
        evidence.get("verification_status") == "pass",
        f"{evidence_path} verification_status must be pass",
    )
    _require(
        errors,
        evidence.get("hash_algorithm") == "sha256",
        f"{evidence_path} hash_algorithm must be sha256",
    )
    _require(
        errors,
        evidence.get("evidence_hash") == summary_pack.get("evidence_hash"),
        f"{evidence_path} evidence_hash must match summary evidence_hash",
    )
    _require(
        errors,
        evidence.get("decision_id") == summary_pack.get("decision_id"),
        f"{evidence_path} decision_id must match summary evidence_pack.decision_id",
    )
    _require(
        errors,
        evidence.get("project_id") == summary.get("project_id"),
        f"{evidence_path} project_id must match summary project_id",
    )
    _require(
        errors,
        evidence_call.get("id") == summary.get("call_id"),
        f"{evidence_path} call.id must match summary call_id",
    )
    _require(
        errors,
        bool(evidence.get("audit_log") or []),
        f"{evidence_path} must include at least one audit log event",
    )
    _require(
        errors,
        bool(matched_outcomes),
        f"{evidence_path} must include at least one matched outcome reconciliation",
    )

    return errors


def validate_artifacts(summary_path: Path, evidence_path: Path | None = None) -> dict[str, Any]:
    summary = _load_json(summary_path)
    if not isinstance(summary, dict):
        raise ValueError(f"{summary_path} must contain a JSON object")

    errors = validate_summary(summary)
    if evidence_path is not None:
        evidence = _load_json(evidence_path)
        if not isinstance(evidence, dict):
            errors.append(f"{evidence_path} must contain a JSON object")
        else:
            errors.extend(validate_evidence(summary, evidence, evidence_path))

    if errors:
        formatted = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"owner proof artifact failed validation:\n{formatted}")

    return summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a live design-partner owner proof artifact before paid launch."
        )
    )
    parser.add_argument(
        "--summary",
        required=True,
        type=Path,
        help="Path to design-partner-owner-proof-summary.json.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="Optional path to design-partner-owner-proof-evidence.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = validate_artifacts(args.summary, args.evidence)
    except ValueError as exc:
        print(f"[owner-proof] failed: {exc}", file=sys.stderr)
        return 1

    evidence_hash = (summary.get("evidence_pack") or {}).get("evidence_hash")
    print(
        "[owner-proof] passed "
        f"project_id={summary.get('project_id')} "
        f"scenario={summary.get('scenario')} "
        f"evidence_hash={evidence_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
