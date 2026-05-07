from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DiagnosisJob, DiagnosisPullRequest, FixEvent
from app.services.fix_adoption import (
    ensure_fix_event_prerequisites,
    fix_event_metadata,
    mark_resolved_if_no_recurrence,
    record_fix_event,
)
from app.services.fix_identity import extract_fix_id_from_result, normalize_fix_id, safe_json_object
from app.services.privacy import mask_metadata

TRACKING_MARKER_RE = re.compile(r"<!--\s*zroky:fix-tracking\s+({.*?})\s*-->", re.DOTALL)
FAILED_CI_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
PASSED_CI_CONCLUSIONS = {"success"}


@dataclass(frozen=True)
class FixTrackingTarget:
    project_id: str
    diagnosis_id: str
    fix_id: str
    link: DiagnosisPullRequest | None = None


def build_zroky_tracking_marker(*, project_id: str, diagnosis_id: str, fix_id: str) -> str:
    payload = {
        "project_id": project_id,
        "diagnosis_id": diagnosis_id,
        "fix_id": fix_id,
    }
    return f"<!-- zroky:fix-tracking {json.dumps(payload, separators=(',', ':'))} -->"


def append_zroky_tracking_marker(
    body: str,
    *,
    project_id: str,
    diagnosis_id: str,
    fix_id: str,
) -> str:
    if TRACKING_MARKER_RE.search(body):
        return body
    return f"{body.rstrip()}\n\n{build_zroky_tracking_marker(project_id=project_id, diagnosis_id=diagnosis_id, fix_id=fix_id)}"


def extract_zroky_tracking_marker(body: Any) -> dict[str, str]:
    if not isinstance(body, str):
        return {}
    match = TRACKING_MARKER_RE.search(body)
    if match is None:
        return {}
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    project_id = str(payload.get("project_id") or "").strip()
    diagnosis_id = str(payload.get("diagnosis_id") or "").strip()
    fix_id = normalize_fix_id(payload.get("fix_id"))
    if not project_id or not diagnosis_id or not fix_id:
        return {}
    return {
        "project_id": project_id,
        "diagnosis_id": diagnosis_id,
        "fix_id": fix_id,
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_github_timestamp(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            return _as_utc(datetime.fromisoformat(raw))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _repository_identity(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    repository = _as_mapping(payload.get("repository"))
    owner = _as_mapping(repository.get("owner"))
    full_name = _as_text(repository.get("full_name"))
    owner_name = _as_text(owner.get("login")) or _as_text(owner.get("name"))
    repo_name = _as_text(repository.get("name"))
    if (not owner_name or not repo_name) and full_name and "/" in full_name:
        owner_name, repo_name = full_name.split("/", 1)
    return owner_name, repo_name, full_name


def _sender_login(payload: dict[str, Any]) -> str | None:
    sender = _as_mapping(payload.get("sender"))
    return _as_text(sender.get("login"))


def _find_link_by_pr(
    db: Session,
    *,
    repository_owner: str | None,
    repository_name: str | None,
    pull_request_number: int | None,
) -> DiagnosisPullRequest | None:
    if not repository_owner or not repository_name or not pull_request_number:
        return None
    return db.execute(
        select(DiagnosisPullRequest)
        .where(
            func.lower(DiagnosisPullRequest.repository_owner) == repository_owner.lower(),
            func.lower(DiagnosisPullRequest.repository_name) == repository_name.lower(),
            DiagnosisPullRequest.pull_request_number == pull_request_number,
        )
        .order_by(DiagnosisPullRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _find_link_by_branch(
    db: Session,
    *,
    repository_owner: str | None,
    repository_name: str | None,
    branch_name: str | None,
) -> DiagnosisPullRequest | None:
    if not repository_owner or not repository_name or not branch_name:
        return None
    return db.execute(
        select(DiagnosisPullRequest)
        .where(
            func.lower(DiagnosisPullRequest.repository_owner) == repository_owner.lower(),
            func.lower(DiagnosisPullRequest.repository_name) == repository_name.lower(),
            DiagnosisPullRequest.branch_name == branch_name,
        )
        .order_by(DiagnosisPullRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _infer_fix_id_for_link(db: Session, link: DiagnosisPullRequest) -> str:
    fix_id = normalize_fix_id(link.fix_id)
    if fix_id:
        return fix_id

    job = db.execute(
        select(DiagnosisJob).where(
            DiagnosisJob.tenant_id == link.tenant_id,
            DiagnosisJob.diagnosis_id == link.diagnosis_id,
        )
    ).scalar_one_or_none()
    result_payload = safe_json_object(job.result_json) if job is not None else {}
    fix_id = extract_fix_id_from_result(result_payload, diagnosis_id=link.diagnosis_id)
    link.fix_id = fix_id
    db.add(link)
    return fix_id


def _target_from_link(db: Session, link: DiagnosisPullRequest) -> FixTrackingTarget:
    return FixTrackingTarget(
        project_id=link.tenant_id,
        diagnosis_id=link.diagnosis_id,
        fix_id=_infer_fix_id_for_link(db, link),
        link=link,
    )


def _target_from_pr_marker(db: Session, pull_request: dict[str, Any]) -> FixTrackingTarget | None:
    marker = extract_zroky_tracking_marker(pull_request.get("body"))
    if not marker:
        return None
    job_exists = db.execute(
        select(DiagnosisJob.diagnosis_id)
        .where(
            DiagnosisJob.tenant_id == marker["project_id"],
            DiagnosisJob.diagnosis_id == marker["diagnosis_id"],
        )
        .limit(1)
    ).scalar_one_or_none()
    if job_exists is None:
        return None
    return FixTrackingTarget(
        project_id=marker["project_id"],
        diagnosis_id=marker["diagnosis_id"],
        fix_id=marker["fix_id"],
        link=None,
    )


def _has_fix_event(
    db: Session,
    target: FixTrackingTarget,
    event_types: set[str],
) -> bool:
    return db.execute(
        select(FixEvent.id)
        .where(
            FixEvent.project_id == target.project_id,
            FixEvent.fix_id == target.fix_id,
            FixEvent.event_type.in_(event_types),
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def _record_event(
    db: Session,
    *,
    target: FixTrackingTarget,
    event_type: str,
    timestamp: datetime,
    metadata: dict[str, Any],
    idempotency_key: str,
) -> FixEvent:
    ensure_fix_event_prerequisites(
        db,
        project_id=target.project_id,
        diagnosis_id=target.diagnosis_id,
        fix_id=target.fix_id,
        event_type=event_type,
        anchor_time=timestamp,
        source="github_webhook",
        inferred_from=event_type,
        metadata={"feed": "github_webhook"},
    )
    return record_fix_event(
        db,
        project_id=target.project_id,
        diagnosis_id=target.diagnosis_id,
        fix_id=target.fix_id,
        event_type=event_type,
        metadata=metadata,
        idempotency_key=idempotency_key,
        source="github_webhook",
        timestamp=timestamp,
    )


def _record_pr_merged(
    db: Session,
    *,
    target: FixTrackingTarget,
    repository_owner: str | None,
    repository_name: str | None,
    pull_request: dict[str, Any],
    delivery_id: str | None,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    pr_number = int(pull_request.get("number") or 0)
    merge_commit_sha = _as_text(pull_request.get("merge_commit_sha"))
    merged_at = _parse_github_timestamp(
        pull_request.get("merged_at") or pull_request.get("updated_at") or pull_request.get("closed_at")
    )

    if target.link is not None:
        target.link.fix_id = target.fix_id
        target.link.merge_commit_sha = merge_commit_sha
        target.link.merged_at = merged_at
        db.add(target.link)

    metadata = mask_metadata(
        {
            "github_event": "pull_request",
            "github_action": "closed",
            "github_delivery_id": delivery_id,
            "github_repository": f"{repository_owner}/{repository_name}" if repository_owner and repository_name else None,
            "github_pr_number": pr_number,
            "github_pr_url": pull_request.get("html_url"),
            "github_merge_commit_sha": merge_commit_sha,
            "github_sender": _sender_login(payload),
        }
    )
    event = _record_event(
        db,
        target=target,
        event_type="pr_merged",
        timestamp=merged_at,
        metadata=metadata,
        idempotency_key=f"github:pull_request:{repository_owner}/{repository_name}:{pr_number}:merged:{merge_commit_sha or merged_at.isoformat()}",
    )
    evaluation, resolved_event = mark_resolved_if_no_recurrence(
        db,
        project_id=target.project_id,
        diagnosis_id=target.diagnosis_id,
        fix_id=target.fix_id,
        since=event.timestamp,
        correlation_signal="pr_merged",
    )

    recorded = [
        {
            "event_type": event.event_type,
            "fix_id": event.fix_id,
            "diagnosis_id": event.diagnosis_id,
            "event_id": event.id,
            "metadata": fix_event_metadata(event),
        }
    ]
    if resolved_event is not None:
        recorded.append(
            {
                "event_type": resolved_event.event_type,
                "fix_id": resolved_event.fix_id,
                "diagnosis_id": resolved_event.diagnosis_id,
                "event_id": resolved_event.id,
                "metadata": fix_event_metadata(resolved_event),
            }
        )
    elif evaluation.reason:
        recorded[0]["resolution_status"] = evaluation.reason
    return recorded


def _targets_for_pr_numbers(
    db: Session,
    *,
    repository_owner: str | None,
    repository_name: str | None,
    pull_requests: list[Any],
    branch_name: str | None,
) -> list[FixTrackingTarget]:
    targets: list[FixTrackingTarget] = []
    seen: set[tuple[str, str]] = set()
    for item in pull_requests:
        pr = _as_mapping(item)
        number = pr.get("number")
        try:
            pr_number = int(number)
        except (TypeError, ValueError):
            continue
        link = _find_link_by_pr(
            db,
            repository_owner=repository_owner,
            repository_name=repository_name,
            pull_request_number=pr_number,
        )
        if link is None:
            continue
        target = _target_from_link(db, link)
        key = (target.project_id, target.fix_id)
        if key not in seen:
            seen.add(key)
            targets.append(target)

    if not targets:
        link = _find_link_by_branch(
            db,
            repository_owner=repository_owner,
            repository_name=repository_name,
            branch_name=branch_name,
        )
        if link is not None:
            targets.append(_target_from_link(db, link))

    return targets


def _record_ci_signal(
    db: Session,
    *,
    target: FixTrackingTarget,
    signal_name: str,
    signal_payload: dict[str, Any],
    repository_owner: str | None,
    repository_name: str | None,
    delivery_id: str | None,
    full_payload: dict[str, Any],
) -> dict[str, Any] | None:
    status = str(signal_payload.get("status") or "").strip().lower()
    conclusion = str(signal_payload.get("conclusion") or "").strip().lower()
    if status and status != "completed":
        return None
    if conclusion not in FAILED_CI_CONCLUSIONS.union(PASSED_CI_CONCLUSIONS):
        return None

    completed_at = _parse_github_timestamp(signal_payload.get("completed_at") or signal_payload.get("updated_at"))
    signal_id = str(signal_payload.get("id") or signal_payload.get("run_number") or signal_payload.get("run_id") or completed_at.isoformat())
    signal_url = signal_payload.get("html_url") or signal_payload.get("details_url")

    if target.link is not None:
        target.link.fix_id = target.fix_id
        target.link.last_ci_state = status or "completed"
        target.link.last_ci_conclusion = conclusion
        target.link.last_ci_completed_at = completed_at
        db.add(target.link)

    applied_or_merged = bool(
        (target.link is not None and target.link.merged_at is not None)
        or _has_fix_event(db, target, {"pr_merged", "applied", "resolved"})
    )
    if not applied_or_merged:
        if target.link is not None:
            db.commit()
        return {
            "ignored_reason": "pre_merge_ci_signal",
            "fix_id": target.fix_id,
            "diagnosis_id": target.diagnosis_id,
            "conclusion": conclusion,
        }

    if (
        target.link is not None
        and target.link.merged_at is not None
        and not _has_fix_event(db, target, {"pr_merged", "applied", "resolved"})
    ):
        _record_event(
            db,
            target=target,
            event_type="pr_merged",
            timestamp=target.link.merged_at,
            metadata={
                "github_event": signal_name,
                "github_repository": f"{repository_owner}/{repository_name}" if repository_owner and repository_name else None,
                "github_pr_number": target.link.pull_request_number,
                "github_merge_commit_sha": target.link.merge_commit_sha,
                "inferred_from": "merged_pr_ci_signal",
            },
            idempotency_key=f"github:{signal_name}:{signal_id}:{target.fix_id}:inferred-pr-merged",
        )

    metadata = mask_metadata(
        {
            "github_event": signal_name,
            "github_delivery_id": delivery_id,
            "github_repository": f"{repository_owner}/{repository_name}" if repository_owner and repository_name else None,
            "github_ci_status": status or "completed",
            "github_ci_conclusion": conclusion,
            "github_ci_signal_id": signal_id,
            "github_ci_url": signal_url,
            "github_head_sha": signal_payload.get("head_sha"),
            "github_head_branch": signal_payload.get("head_branch"),
            "github_sender": _sender_login(full_payload),
        }
    )

    if conclusion in FAILED_CI_CONCLUSIONS:
        event = _record_event(
            db,
            target=target,
            event_type="regressed",
            timestamp=completed_at,
            metadata={
                **metadata,
                "regression_confidence": 0.9,
                "regression_severity": "major" if conclusion in {"failure", "startup_failure"} else "minor",
                "regression_signal": signal_name,
                "reason": "github_ci_failed_after_fix_applied",
            },
            idempotency_key=f"github:{signal_name}:{signal_id}:{target.fix_id}:regressed",
        )
        return {
            "event_type": event.event_type,
            "fix_id": event.fix_id,
            "diagnosis_id": event.diagnosis_id,
            "event_id": event.id,
            "metadata": fix_event_metadata(event),
        }

    event = _record_event(
        db,
        target=target,
        event_type="resolved",
        timestamp=completed_at,
        metadata={
            **metadata,
            "resolution_confidence": 0.75,
            "resolution_correlation": "medium",
            "attribution_mode": "ci_verification",
            "confidence_calibration": "github_ci_success",
            "resolution_window": "ci_signal",
            "checked_calls": 0,
            "recurrence_count": 0,
            "target_categories": [],
            "reason": "github_ci_passed_after_fix_applied",
        },
        idempotency_key=f"github:{signal_name}:{signal_id}:{target.fix_id}:resolved",
    )
    return {
        "event_type": event.event_type,
        "fix_id": event.fix_id,
        "diagnosis_id": event.diagnosis_id,
        "event_id": event.id,
        "metadata": fix_event_metadata(event),
    }


def process_github_webhook_event(
    db: Session,
    *,
    event_name: str,
    payload: dict[str, Any],
    delivery_id: str | None = None,
) -> dict[str, Any]:
    normalized_event = event_name.strip().lower()
    repository_owner, repository_name, repository_full_name = _repository_identity(payload)
    recorded: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []

    if normalized_event == "pull_request":
        action = str(payload.get("action") or "").strip().lower()
        pull_request = _as_mapping(payload.get("pull_request"))
        merged = bool(pull_request.get("merged"))
        if action != "closed" or not merged:
            return {
                "handled": True,
                "ignored_reason": "pull_request_not_merged",
                "recorded_events": [],
            }

        pr_number = int(pull_request.get("number") or 0)
        link = _find_link_by_pr(
            db,
            repository_owner=repository_owner,
            repository_name=repository_name,
            pull_request_number=pr_number,
        )
        target = _target_from_link(db, link) if link is not None else _target_from_pr_marker(db, pull_request)
        if target is None:
            return {
                "handled": True,
                "ignored_reason": "zroky_fix_target_not_found",
                "recorded_events": [],
            }

        recorded.extend(
            _record_pr_merged(
                db,
                target=target,
                repository_owner=repository_owner,
                repository_name=repository_name,
                pull_request=pull_request,
                delivery_id=delivery_id,
                payload=payload,
            )
        )
        return {
            "handled": True,
            "repository": repository_full_name,
            "recorded_events": recorded,
        }

    if normalized_event in {"check_run", "workflow_run"}:
        signal_payload = _as_mapping(payload.get(normalized_event))
        pull_requests = signal_payload.get("pull_requests")
        if not isinstance(pull_requests, list):
            pull_requests = []
        branch_name = _as_text(signal_payload.get("head_branch"))
        targets = _targets_for_pr_numbers(
            db,
            repository_owner=repository_owner,
            repository_name=repository_name,
            pull_requests=pull_requests,
            branch_name=branch_name,
        )
        if not targets:
            return {
                "handled": True,
                "ignored_reason": "zroky_fix_target_not_found",
                "recorded_events": [],
            }
        for target in targets:
            result = _record_ci_signal(
                db,
                target=target,
                signal_name=normalized_event,
                signal_payload=signal_payload,
                repository_owner=repository_owner,
                repository_name=repository_name,
                delivery_id=delivery_id,
                full_payload=payload,
            )
            if result is None:
                continue
            if "event_type" in result:
                recorded.append(result)
            else:
                ignored.append(result)
        return {
            "handled": True,
            "repository": repository_full_name,
            "recorded_events": recorded,
            "ignored": ignored,
        }

    return {
        "handled": False,
        "ignored_reason": "unsupported_github_event",
        "recorded_events": [],
    }
