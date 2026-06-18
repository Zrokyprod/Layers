from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRelease,
    Call,
    GoldenSet,
    GoldenTrace,
    RegressionContract,
    RegressionContractVersion,
)
from app.services.golden_contracts import GOLDEN_CONTRACT_KEY, safe_json_object


DEFAULT_REQUIRED_TRIALS = 10
DEFAULT_CRITICAL_TOLERANCE = 0
DEFAULT_TRIAL_POLICY = {
    "required_trials": DEFAULT_REQUIRED_TRIALS,
    "critical_violation_tolerance": DEFAULT_CRITICAL_TOLERANCE,
}


class RegressionContractConflict(Exception):
    pass


class RegressionContractActivationError(Exception):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__(", ".join(blockers))
        self.blockers = blockers


def json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), separators=(",", ":"), sort_keys=True, default=str)


def json_object(raw: str | None) -> dict[str, Any]:
    return safe_json_object(raw)


def list_contracts(
    db: Session,
    *,
    project_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[RegressionContract]:
    stmt = select(RegressionContract).where(RegressionContract.project_id == project_id)
    if status:
        stmt = stmt.where(RegressionContract.status == status)
    return list(
        db.execute(
            stmt.order_by(RegressionContract.created_at.desc(), RegressionContract.id.desc()).limit(limit)
        ).scalars()
    )


def get_contract(
    db: Session,
    *,
    project_id: str,
    contract_id: str,
) -> RegressionContract | None:
    return db.execute(
        select(RegressionContract).where(
            RegressionContract.project_id == project_id,
            RegressionContract.id == contract_id,
        )
    ).scalar_one_or_none()


def create_contract(
    db: Session,
    *,
    project_id: str,
    name: str,
    description: str | None = None,
    severity: str = "medium",
    source_issue_id: str | None = None,
    owner_id: str | None = None,
) -> RegressionContract:
    row = RegressionContract(
        id=str(uuid4()),
        project_id=project_id,
        source_issue_id=source_issue_id,
        name=name.strip(),
        description=description,
        severity=severity,
        status="draft",
        owner_id=owner_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise RegressionContractConflict("contract name already exists for this project") from exc
    return row


def create_contract_version(
    db: Session,
    *,
    project_id: str,
    contract_id: str,
    spec_json: Mapping[str, Any],
    spec_version: str = "regression_contract_v1",
    fixture_set_id: str | None = None,
    baseline_release_id: str | None = None,
    trial_policy: Mapping[str, Any] | None = None,
    evaluator_bundle_version: str = "default-v1",
    created_by: str | None = None,
) -> RegressionContractVersion | None:
    contract = get_contract(db, project_id=project_id, contract_id=contract_id)
    if contract is None:
        return None
    _ensure_fixture_belongs_to_project(db, project_id=project_id, fixture_set_id=fixture_set_id)
    _ensure_release_belongs_to_project(db, project_id=project_id, release_id=baseline_release_id)
    version_number = (
        db.execute(
            select(func.max(RegressionContractVersion.version_number)).where(
                RegressionContractVersion.contract_id == contract_id,
                RegressionContractVersion.project_id == project_id,
            )
        ).scalar()
        or 0
    ) + 1
    policy = _normalize_trial_policy(trial_policy)
    row = RegressionContractVersion(
        id=str(uuid4()),
        contract_id=contract_id,
        project_id=project_id,
        version_number=version_number,
        spec_version=spec_version,
        spec_json=json_dump(spec_json),
        fixture_set_id=fixture_set_id,
        baseline_release_id=baseline_release_id,
        trial_policy_json=json_dump(policy),
        evaluator_bundle_version=evaluator_bundle_version,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def activate_contract_version(
    db: Session,
    *,
    project_id: str,
    contract_id: str,
    version_id: str,
    approved_by: str | None,
) -> RegressionContractVersion | None:
    contract = get_contract(db, project_id=project_id, contract_id=contract_id)
    if contract is None:
        return None
    version = db.execute(
        select(RegressionContractVersion).where(
            RegressionContractVersion.project_id == project_id,
            RegressionContractVersion.contract_id == contract_id,
            RegressionContractVersion.id == version_id,
        )
    ).scalar_one_or_none()
    if version is None:
        return None

    blockers = activation_blockers(version)
    if blockers:
        raise RegressionContractActivationError(blockers)

    now = datetime.now(timezone.utc)
    version.approved_by = approved_by
    version.approved_at = now
    contract.status = "active"
    contract.active_version_id = version.id
    contract.updated_at = now
    db.add(version)
    db.add(contract)
    db.commit()
    db.refresh(version)
    return version


def activation_blockers(version: RegressionContractVersion) -> list[str]:
    blockers: list[str] = []
    spec = json_object(version.spec_json)
    proof = spec.get("proof") if isinstance(spec.get("proof"), dict) else {}
    policy = _normalize_trial_policy(json_object(version.trial_policy_json))
    required_trials = int(policy["required_trials"])
    critical_tolerance = int(policy["critical_violation_tolerance"])

    if not version.fixture_set_id:
        blockers.append("fixture_set_required")
    if not version.baseline_release_id:
        blockers.append("baseline_release_required")
    if not proof.get("baseline_reproduced"):
        blockers.append("baseline_reproduction_required")
    if not proof.get("candidate_verified"):
        blockers.append("candidate_verification_required")
    if int(proof.get("required_trials") or 0) < required_trials:
        blockers.append("required_trials_not_completed")
    if int(proof.get("critical_violations") or 0) > critical_tolerance:
        blockers.append("critical_violations_present")
    if not proof.get("fixture_pinned"):
        blockers.append("fixture_pin_required")
    if not proof.get("evaluator_bundle_pinned"):
        blockers.append("evaluator_bundle_pin_required")
    if not proof.get("candidate_sha"):
        blockers.append("candidate_sha_required")
    return blockers


def import_golden_contracts(
    db: Session,
    *,
    project_id: str,
    created_by: str | None = None,
) -> list[RegressionContractVersion]:
    rows = db.execute(
        select(GoldenTrace, GoldenSet, Call)
        .join(GoldenSet, GoldenSet.id == GoldenTrace.golden_set_id)
        .join(Call, Call.id == GoldenTrace.call_id, isouter=True)
        .where(GoldenTrace.project_id == project_id, GoldenSet.project_id == project_id)
        .order_by(GoldenSet.created_at.desc(), GoldenTrace.created_at.desc())
    ).all()
    imported: list[RegressionContractVersion] = []
    for trace, golden_set, call in rows:
        criteria = json_object(trace.criteria_json)
        contract_spec = criteria.get(GOLDEN_CONTRACT_KEY)
        if not isinstance(contract_spec, dict):
            continue
        name = _contract_name(golden_set.name, trace.id)
        contract = db.execute(
            select(RegressionContract).where(
                RegressionContract.project_id == project_id,
                RegressionContract.name == name,
            )
        ).scalar_one_or_none()
        if contract is None:
            contract = RegressionContract(
                id=str(uuid4()),
                project_id=project_id,
                name=name,
                description=f"Imported from fixture set {golden_set.name}",
                severity=_severity(contract_spec),
                status="draft",
                owner_id=created_by,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(contract)
            db.flush()
        existing = db.execute(
            select(RegressionContractVersion).where(
                RegressionContractVersion.project_id == project_id,
                RegressionContractVersion.contract_id == contract.id,
                RegressionContractVersion.fixture_set_id == golden_set.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        version = create_contract_version(
            db,
            project_id=project_id,
            contract_id=contract.id,
            spec_json={"schema": "regression_contract_v1", "imported_from": "golden_contract_v1", **contract_spec},
            fixture_set_id=golden_set.id,
            baseline_release_id=call.agent_release_id if call is not None else None,
            created_by=created_by,
        )
        if version is not None:
            imported.append(version)
    return imported


def _ensure_fixture_belongs_to_project(
    db: Session,
    *,
    project_id: str,
    fixture_set_id: str | None,
) -> None:
    if not fixture_set_id:
        return
    exists = db.execute(
        select(GoldenSet.id).where(GoldenSet.project_id == project_id, GoldenSet.id == fixture_set_id)
    ).first()
    if exists is None:
        raise ValueError("fixture_set_id does not belong to this project")


def _ensure_release_belongs_to_project(
    db: Session,
    *,
    project_id: str,
    release_id: str | None,
) -> None:
    if not release_id:
        return
    exists = db.execute(
        select(AgentRelease.id).where(AgentRelease.project_id == project_id, AgentRelease.id == release_id)
    ).first()
    if exists is None:
        raise ValueError("baseline_release_id does not belong to this project")


def _normalize_trial_policy(policy: Mapping[str, Any] | None) -> dict[str, int]:
    policy = policy or {}
    return {
        "required_trials": max(DEFAULT_REQUIRED_TRIALS, int(policy.get("required_trials") or DEFAULT_REQUIRED_TRIALS)),
        "critical_violation_tolerance": int(
            policy.get("critical_violation_tolerance")
            if policy.get("critical_violation_tolerance") is not None
            else DEFAULT_CRITICAL_TOLERANCE
        ),
    }


def _contract_name(set_name: str, trace_id: str) -> str:
    return f"{set_name.strip() or 'Fixture'} / {trace_id[:8]}"


def _severity(spec: Mapping[str, Any]) -> str:
    severity = str(spec.get("severity") or "medium").strip().lower()
    return severity if severity in {"low", "medium", "high", "critical"} else "medium"
