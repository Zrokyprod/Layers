"""consolidate legacy issues into canonical anomalies.

Revision ID: 0072_consolidate_issues_into_anomalies
Revises: 0071_create_tenant_teams_install
Create Date: 2026-05-25 00:00:00.000000
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0072_consolidate_issues_into_anomalies"
down_revision = "0071_create_tenant_teams_install"
branch_labels = None
depends_on = None


_DETECTORS = (
    "LOOP_DETECTED",
    "COST_SPIKE",
    "ACCURACY_REGRESSION",
    "HALLUCINATION_RISK",
    "SCHEMA_VIOLATION",
    "LATENCY_REGRESSION",
    "TOOL_SELECTION_FAILURE",
    "TOOL_CALL_FAILURE",
    "TOOL_ARGUMENT_MISMATCH",
    "RAG_RETRIEVAL_MISSING",
    "RETRIEVAL_MISSING",
    "TOKEN_USAGE_DRIFT",
    "TOKEN_OVERFLOW",
    "RATE_LIMIT",
    "AUTH_FAILURE",
    "PROVIDER_ERROR",
    "LATENCY_ANOMALY",
    "LATENCY_DRIFT",
    "ERROR_RATE_DRIFT",
    "EMPTY_OUTPUT",
    "OUTPUT_TRUNCATED",
    "OUTPUT_LENGTH_DRIFT",
    "REPEATED_OUTPUT",
    "UNKNOWN",
)

_FAILURE_TO_DETECTOR = {
    "HALLUCINATION": "HALLUCINATION_RISK",
    "SCHEMA_MISMATCH": "SCHEMA_VIOLATION",
}


def _detector_for(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        return "UNKNOWN"
    mapped = _FAILURE_TO_DETECTOR.get(normalized, normalized)
    if mapped in _DETECTORS:
        return mapped
    if "TOOL" in normalized:
        return "TOOL_SELECTION_FAILURE"
    if "RAG" in normalized or "RETRIEVAL" in normalized:
        return "RAG_RETRIEVAL_MISSING"
    if "LATENCY" in normalized:
        return "LATENCY_DRIFT"
    if "TOKEN" in normalized:
        return "TOKEN_USAGE_DRIFT"
    if "OUTPUT" in normalized:
        return "ACCURACY_REGRESSION"
    return "UNKNOWN"


def _fingerprint(
    *,
    detector: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
) -> str:
    payload = "|".join(
        [
            detector.strip().upper(),
            (prompt_fingerprint or "").strip(),
            (agent_name or "").strip(),
            "",
        ]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item]


def _issue_status_to_anomaly(status: str | None) -> str:
    value = (status or "").lower()
    if value == "resolved":
        return "resolved"
    if value == "ignored":
        return "muted"
    return "open"


def _build_evidence(row: sa.engine.RowMapping, existing_json: str | None = None) -> str:
    sample = _json_object(row.get("sample_evidence_json"))
    existing = _json_object(existing_json)
    evidence = dict(existing)
    evidence.update(sample)
    evidence.update(
        {
            "failure_code": row["failure_code"],
            "prompt_fingerprint": row["prompt_fingerprint"],
            "agent_name": row["agent_name"],
            "blast_radius_usd": float(row["blast_radius_usd"] or 0.0),
            "legacy_issue": {
                "failure_code": row["failure_code"],
                "prompt_fingerprint": row["prompt_fingerprint"],
                "agent_name": row["agent_name"],
                "sample_call_id": row["sample_call_id"],
                "sample_diagnosis_id": row["sample_diagnosis_id"],
                "blast_radius_usd": float(row["blast_radius_usd"] or 0.0),
                "sample_evidence_json": row["sample_evidence_json"],
                "last_fix_id": row["last_fix_id"],
                "resolved_at": row["resolved_at"].isoformat()
                if row["resolved_at"] is not None
                else None,
                "resolution_source": row["resolution_source"],
            },
        }
    )
    return json.dumps(evidence, separators=(",", ":"))


def _merge_sample_ids(existing_json: str | None, sample_call_id: str | None) -> str | None:
    ids = _json_list(existing_json)
    if sample_call_id and sample_call_id not in ids:
        ids.append(sample_call_id)
    ids = ids[-5:]
    return json.dumps(ids, separators=(",", ":")) if ids else None


def _expand_detector_constraint() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    detector_sql = ", ".join(f"'{item}'" for item in _DETECTORS)
    op.execute("ALTER TABLE anomalies DROP CONSTRAINT IF EXISTS ck_anomalies_detector")
    op.create_check_constraint(
        "ck_anomalies_detector",
        "anomalies",
        f"detector IN ({detector_sql})",
    )


def upgrade() -> None:
    _expand_detector_constraint()
    conn = op.get_bind()
    issue_rows = conn.execute(
        sa.text(
            """
            SELECT id, project_id, failure_code, prompt_fingerprint, agent_name,
                   status, severity, occurrence_count, blast_radius_usd,
                   first_seen_at, last_seen_at, sample_call_id,
                   sample_diagnosis_id, sample_evidence_json, last_fix_id,
                   resolved_at, resolution_source, created_at, updated_at
            FROM issues
            """
        )
    ).mappings().all()

    for row in issue_rows:
        detector = _detector_for(row["failure_code"])
        fingerprint = _fingerprint(
            detector=detector,
            prompt_fingerprint=row["prompt_fingerprint"],
            agent_name=row["agent_name"],
        )
        existing = conn.execute(
            sa.text(
                """
                SELECT id, occurrence_count, first_seen_at, last_seen_at,
                       sample_call_ids_json, evidence_json
                FROM anomalies
                WHERE project_id = :project_id AND fingerprint = :fingerprint
                """
            ),
            {"project_id": row["project_id"], "fingerprint": fingerprint},
        ).mappings().first()
        evidence_json = _build_evidence(
            row,
            existing["evidence_json"] if existing is not None else None,
        )
        sample_ids_json = _merge_sample_ids(
            existing["sample_call_ids_json"] if existing is not None else None,
            row["sample_call_id"],
        )
        anomaly_status = _issue_status_to_anomaly(row["status"])

        if existing is not None:
            conn.execute(
                sa.text(
                    """
                    UPDATE anomalies
                    SET severity = :severity,
                        status = :status,
                        occurrence_count = :occurrence_count,
                        first_seen_at = CASE
                            WHEN first_seen_at <= :first_seen_at THEN first_seen_at
                            ELSE :first_seen_at
                        END,
                        last_seen_at = CASE
                            WHEN last_seen_at >= :last_seen_at THEN last_seen_at
                            ELSE :last_seen_at
                        END,
                        sample_call_ids_json = :sample_call_ids_json,
                        evidence_json = :evidence_json,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing["id"],
                    "severity": row["severity"],
                    "status": anomaly_status,
                    "occurrence_count": max(
                        int(existing["occurrence_count"] or 0),
                        int(row["occurrence_count"] or 0),
                    ),
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "sample_call_ids_json": sample_ids_json,
                    "evidence_json": evidence_json,
                    "updated_at": row["updated_at"],
                },
            )
            continue

        conn.execute(
            sa.text(
                """
                INSERT INTO anomalies (
                    id, project_id, fingerprint, detector, severity, status,
                    first_seen_at, last_seen_at, occurrence_count,
                    sample_call_ids_json, evidence_json, created_at, updated_at
                )
                VALUES (
                    :id, :project_id, :fingerprint, :detector, :severity, :status,
                    :first_seen_at, :last_seen_at, :occurrence_count,
                    :sample_call_ids_json, :evidence_json, :created_at, :updated_at
                )
                """
            ),
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "fingerprint": fingerprint,
                "detector": detector,
                "severity": row["severity"],
                "status": anomaly_status,
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "occurrence_count": row["occurrence_count"],
                "sample_call_ids_json": sample_ids_json,
                "evidence_json": evidence_json,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    detector_sql = ", ".join(
        f"'{item}'"
        for item in (
            "LOOP_DETECTED",
            "COST_SPIKE",
            "ACCURACY_REGRESSION",
            "HALLUCINATION_RISK",
            "SCHEMA_VIOLATION",
            "LATENCY_REGRESSION",
        )
    )
    op.execute("ALTER TABLE anomalies DROP CONSTRAINT IF EXISTS ck_anomalies_detector")
    op.create_check_constraint(
        "ck_anomalies_detector",
        "anomalies",
        f"detector IN ({detector_sql})",
    )
