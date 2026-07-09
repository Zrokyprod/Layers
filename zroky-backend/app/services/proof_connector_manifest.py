"""Proof-first connector manifest evaluation.

This module is intentionally pure: it does not fetch from a source of record and
does not know about SQLAlchemy. Existing connectors can keep doing the I/O; this
layer decides whether the observed record is strong enough evidence for a
receipt.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


PROOF_MATCHED = "matched"
PROOF_MISMATCHED = "mismatched"
PROOF_PENDING = "pending"
PROOF_UNVERIFIABLE = "unverifiable"
PROOF_PARTIAL = "partial"

VALID_PROOF_STATUSES = frozenset(
    {
        PROOF_MATCHED,
        PROOF_MISMATCHED,
        PROOF_PENDING,
        PROOF_UNVERIFIABLE,
        PROOF_PARTIAL,
    }
)


@dataclass(frozen=True)
class ProofFieldResult:
    kind: str
    field: str
    expected: Any
    actual: Any
    matched: bool
    required: bool = True
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "matched": self.matched,
            "required": self.required,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProofEvaluation:
    status: str
    reason: str
    fields: list[ProofFieldResult]
    observed_at: datetime | None = None
    action_time: datetime | None = None
    verification_window_seconds: int | None = None
    connector_retryable: bool | None = None

    @property
    def matched_fields(self) -> list[dict[str, Any]]:
        return [field.to_json() for field in self.fields if field.matched]

    @property
    def mismatches(self) -> list[dict[str, Any]]:
        return [
            field.to_json()
            for field in self.fields
            if not field.matched and field.reason not in {"missing_expected", "missing_actual"}
        ]

    @property
    def missing_fields(self) -> list[str]:
        return [
            field.field
            for field in self.fields
            if not field.matched and field.reason in {"missing_expected", "missing_actual"}
        ]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "fields": [field.to_json() for field in self.fields],
            "matched_fields": self.matched_fields,
            "mismatches": self.mismatches,
            "missing_fields": self.missing_fields,
            "observed_at": _iso(self.observed_at),
            "action_time": _iso(self.action_time),
            "verification_window_seconds": self.verification_window_seconds,
            "connector_retryable": self.connector_retryable,
            "point_in_time": True,
        }


@dataclass(frozen=True)
class VerificationCoverageSummary:
    total: int
    matched: int
    mismatched: int
    pending: int
    unverifiable: int
    partial: int

    @property
    def sor_matched(self) -> int:
        return self.matched

    @property
    def covered(self) -> int:
        return self.matched + self.mismatched + self.partial

    @property
    def coverage_percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round((self.sor_matched / self.total) * 100, 2)

    @property
    def evidence_coverage_percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round((self.covered / self.total) * 100, 2)

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "matched": self.matched,
            "mismatched": self.mismatched,
            "pending": self.pending,
            "unverifiable": self.unverifiable,
            "partial": self.partial,
            "sor_matched": self.sor_matched,
            "covered": self.covered,
            "coverage_percent": self.coverage_percent,
            "evidence_coverage_percent": self.evidence_coverage_percent,
        }


def evaluate_proof_manifest(
    *,
    claimed: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
    manifest: Mapping[str, Any] | None,
    actual_record_found: bool | None = None,
    connector_metadata: Mapping[str, Any] | None = None,
    checked_at: datetime | None = None,
) -> ProofEvaluation:
    manifest_dict = _as_dict(manifest)
    temporal = _as_dict(manifest_dict.get("temporal") or manifest_dict.get("observation"))
    causal = _as_dict(manifest_dict.get("causal") or manifest_dict.get("causal_evidence"))
    connector = _as_dict(connector_metadata)
    now = _as_utc(checked_at) or _now()
    action_time = _resolve_time(temporal.get("action_time"), claimed)
    window_seconds = _positive_int(
        temporal.get("window_seconds")
        or temporal.get("observe_window_seconds")
        or _as_dict(manifest_dict.get("poll")).get("window_seconds")
    )
    retryable = _metadata_retryable(connector)

    if actual_record_found is False or not actual:
        if _within_open_window(action_time, window_seconds, now) or retryable:
            return ProofEvaluation(
                status=PROOF_PENDING,
                reason="verification_window_open" if not retryable else "connector_retryable",
                fields=[],
                action_time=action_time,
                verification_window_seconds=window_seconds,
                connector_retryable=retryable,
            )
        if actual_record_found is False:
            return ProofEvaluation(
                status=PROOF_MISMATCHED,
                reason="system_of_record_record_missing_after_window",
                fields=[],
                action_time=action_time,
                verification_window_seconds=window_seconds,
                connector_retryable=retryable,
            )
        return ProofEvaluation(
            status=PROOF_UNVERIFIABLE,
            reason="system_of_record_unavailable",
            fields=[],
            action_time=action_time,
            verification_window_seconds=window_seconds,
            connector_retryable=retryable,
        )

    actual_dict = _as_dict(actual)
    fields: list[ProofFieldResult] = []
    fields.extend(_evaluate_match_fields(claimed=claimed, actual=actual_dict, manifest=manifest_dict))
    fields.extend(_evaluate_causal_fields(claimed=claimed, actual=actual_dict, causal=causal))

    observed_at, temporal_result = _evaluate_temporal_rule(
        claimed=claimed,
        actual=actual_dict,
        temporal=temporal,
        action_time=action_time,
        window_seconds=window_seconds,
        checked_at=now,
    )
    if temporal_result is not None:
        fields.append(temporal_result)

    return _classify_evaluation(
        fields=fields,
        observed_at=observed_at,
        action_time=action_time,
        window_seconds=window_seconds,
        retryable=retryable,
    )


def proof_status_to_outcome_verdict(status: str) -> str:
    if status == PROOF_MATCHED:
        return "matched"
    if status in {PROOF_MISMATCHED, PROOF_PARTIAL}:
        return "mismatched"
    return "not_verified"


def public_manifest_summary(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    manifest_dict = _as_dict(manifest)
    if not manifest_dict:
        return {}
    return {
        "schema_version": _text(manifest_dict.get("schema_version")),
        "connector_type": _text(manifest_dict.get("connector_type")),
        "capability": _text(manifest_dict.get("capability")),
        "tier": _text(manifest_dict.get("tier")),
        "match_fields": _manifest_match_field_names(manifest_dict),
        "has_temporal_rule": bool(
            manifest_dict.get("temporal") or manifest_dict.get("observation")
        ),
        "has_causal_rule": bool(
            manifest_dict.get("causal") or manifest_dict.get("causal_evidence")
        ),
    }


def proof_coverage_summary(statuses: Iterable[str]) -> VerificationCoverageSummary:
    counts = {status: 0 for status in VALID_PROOF_STATUSES}
    total = 0
    for raw_status in statuses:
        status = str(raw_status or "").strip().lower()
        if status not in counts:
            status = PROOF_UNVERIFIABLE
        counts[status] += 1
        total += 1
    return VerificationCoverageSummary(
        total=total,
        matched=counts[PROOF_MATCHED],
        mismatched=counts[PROOF_MISMATCHED],
        pending=counts[PROOF_PENDING],
        unverifiable=counts[PROOF_UNVERIFIABLE],
        partial=counts[PROOF_PARTIAL],
    )


def proof_status_from_metadata(metadata: Mapping[str, Any] | None) -> str | None:
    metadata_dict = _as_dict(metadata)
    proof = _as_dict(metadata_dict.get("proof"))
    raw = proof.get("status") or metadata_dict.get("proof_status")
    status = str(raw or "").strip().lower()
    return status if status in VALID_PROOF_STATUSES else None


def _evaluate_match_fields(
    *,
    claimed: Mapping[str, Any],
    actual: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> list[ProofFieldResult]:
    rules = _match_rules(manifest)
    results: list[ProofFieldResult] = []
    for rule in rules:
        claim_field = rule["claim_field"]
        actual_field = rule["actual_field"]
        label = rule["label"]
        required = bool(rule.get("required", True))
        expected_present, expected = _field_value(claimed, claim_field)
        actual_present, actual_value = _field_value(actual, actual_field)
        if not expected_present:
            results.append(
                ProofFieldResult(
                    kind="match",
                    field=label,
                    expected=None,
                    actual=actual_value if actual_present else None,
                    matched=False,
                    required=required,
                    reason="missing_expected",
                )
            )
            continue
        if not actual_present:
            results.append(
                ProofFieldResult(
                    kind="match",
                    field=label,
                    expected=expected,
                    actual=None,
                    matched=False,
                    required=required,
                    reason="missing_actual",
                )
            )
            continue
        matched = _values_equal(expected, actual_value)
        results.append(
            ProofFieldResult(
                kind="match",
                field=label,
                expected=expected,
                actual=actual_value,
                matched=matched,
                required=required,
                reason=None if matched else "field_mismatch",
            )
        )
    return results


def _evaluate_causal_fields(
    *,
    claimed: Mapping[str, Any],
    actual: Mapping[str, Any],
    causal: Mapping[str, Any],
) -> list[ProofFieldResult]:
    rules: list[dict[str, Any]] = []
    actor_field = _text(causal.get("actor_field"))
    expected_actor = causal.get("expected_actor")
    expected_actor_claim_field = _text(causal.get("expected_actor_claim_field"))
    if actor_field and (expected_actor is not None or expected_actor_claim_field):
        rules.append(
            {
                "label": actor_field,
                "actual_field": actor_field,
                "expected": expected_actor,
                "expected_claim_field": expected_actor_claim_field,
                "kind": "causal_actor",
            }
        )
    correlation_field = _text(causal.get("correlation_field"))
    expected_correlation = causal.get("expected_correlation")
    expected_correlation_claim_field = _text(causal.get("expected_correlation_claim_field"))
    if correlation_field and (
        expected_correlation is not None or expected_correlation_claim_field
    ):
        rules.append(
            {
                "label": correlation_field,
                "actual_field": correlation_field,
                "expected": expected_correlation,
                "expected_claim_field": expected_correlation_claim_field,
                "kind": "causal_correlation",
            }
        )

    results: list[ProofFieldResult] = []
    for rule in rules:
        actual_present, actual_value = _field_value(actual, rule["actual_field"])
        expected_present = True
        expected = rule.get("expected")
        expected_claim_field = _text(rule.get("expected_claim_field"))
        if expected is None and expected_claim_field:
            expected_present, expected = _field_value(claimed, expected_claim_field)
        if not expected_present:
            results.append(
                ProofFieldResult(
                    kind=rule["kind"],
                    field=rule["label"],
                    expected=None,
                    actual=actual_value if actual_present else None,
                    matched=False,
                    reason="missing_expected",
                )
            )
            continue
        if not actual_present:
            results.append(
                ProofFieldResult(
                    kind=rule["kind"],
                    field=rule["label"],
                    expected=expected,
                    actual=None,
                    matched=False,
                    reason="missing_actual",
                )
            )
            continue
        matched = _values_equal(expected, actual_value)
        results.append(
            ProofFieldResult(
                kind=rule["kind"],
                field=rule["label"],
                expected=expected,
                actual=actual_value,
                matched=matched,
                reason=None if matched else "causal_mismatch",
            )
        )
    return results


def _evaluate_temporal_rule(
    *,
    claimed: Mapping[str, Any],
    actual: Mapping[str, Any],
    temporal: Mapping[str, Any],
    action_time: datetime | None,
    window_seconds: int | None,
    checked_at: datetime,
) -> tuple[datetime | None, ProofFieldResult | None]:
    observed_at_field = _text(
        temporal.get("observed_at_field")
        or temporal.get("timestamp_field")
        or temporal.get("updated_at_field")
    )
    observed_at = _resolve_time(temporal.get("observed_at"), actual)
    if observed_at is None and observed_at_field:
        present, value = _field_value(actual, observed_at_field)
        if present:
            observed_at = _parse_time(value)
        else:
            return None, ProofFieldResult(
                kind="temporal",
                field=observed_at_field,
                expected="observed timestamp",
                actual=None,
                matched=False,
                reason="missing_actual",
            )
    if observed_at is None:
        return None, None

    action_time = action_time or _resolve_time(temporal.get("must_be_after"), claimed)
    if action_time is None:
        return observed_at, ProofFieldResult(
            kind="temporal",
            field=observed_at_field or "observed_at",
            expected=None,
            actual=_iso(observed_at),
            matched=False,
            reason="missing_expected",
        )
    if observed_at < action_time:
        return observed_at, ProofFieldResult(
            kind="temporal",
            field=observed_at_field or "observed_at",
            expected=f">={_iso(action_time)}",
            actual=_iso(observed_at),
            matched=False,
            reason="observed_before_action",
        )

    deadline = action_time + timedelta(seconds=window_seconds) if window_seconds else None
    if deadline is not None and observed_at > deadline and checked_at >= deadline:
        return observed_at, ProofFieldResult(
            kind="temporal",
            field=observed_at_field or "observed_at",
            expected=f"<={_iso(deadline)}",
            actual=_iso(observed_at),
            matched=False,
            reason="observed_after_window",
        )

    return observed_at, ProofFieldResult(
        kind="temporal",
        field=observed_at_field or "observed_at",
        expected=f">={_iso(action_time)}",
        actual=_iso(observed_at),
        matched=True,
    )


def _classify_evaluation(
    *,
    fields: list[ProofFieldResult],
    observed_at: datetime | None,
    action_time: datetime | None,
    window_seconds: int | None,
    retryable: bool | None,
) -> ProofEvaluation:
    required = [field for field in fields if field.required]
    matched = [field for field in required if field.matched]
    failures = [field for field in required if not field.matched]
    hard_mismatches = [
        field
        for field in failures
        if field.reason
        in {"causal_mismatch", "observed_before_action", "observed_after_window"}
    ]

    if hard_mismatches:
        status = PROOF_MISMATCHED
        reason = hard_mismatches[0].reason or "proof_mismatch"
    elif failures and matched:
        status = PROOF_PARTIAL
        reason = "partial_evidence"
    elif failures:
        status = PROOF_UNVERIFIABLE
        reason = "required_evidence_missing"
    elif required:
        status = PROOF_MATCHED
        reason = "temporal_causal_match" if any(field.kind != "match" for field in required) else "all_required_fields_matched"
    else:
        status = PROOF_UNVERIFIABLE
        reason = "no_required_evidence_rules"

    return ProofEvaluation(
        status=status,
        reason=reason,
        fields=fields,
        observed_at=observed_at,
        action_time=action_time,
        verification_window_seconds=window_seconds,
        connector_retryable=retryable,
    )


def _match_rules(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rules = manifest.get("match_rules")
    if raw_rules is None:
        raw_rules = manifest.get("match")
    rules: list[dict[str, Any]] = []
    if isinstance(raw_rules, list | tuple):
        for item in raw_rules:
            if not isinstance(item, Mapping):
                continue
            claim_field = _text(item.get("claim_field") or item.get("claim") or item.get("field"))
            actual_field = _text(item.get("actual_field") or item.get("actual") or item.get("field"))
            if not claim_field or not actual_field:
                continue
            rules.append(
                {
                    "claim_field": claim_field,
                    "actual_field": actual_field,
                    "label": _text(item.get("label")) or actual_field,
                    "required": item.get("required", True),
                }
            )
    elif isinstance(raw_rules, Mapping):
        for claim_field, actual_field in raw_rules.items():
            claim = _text(claim_field)
            actual = _text(actual_field)
            if claim and actual:
                rules.append(
                    {
                        "claim_field": claim,
                        "actual_field": actual,
                        "label": actual,
                        "required": True,
                    }
                )

    if rules:
        return rules

    fields = manifest.get("match_fields")
    if not isinstance(fields, list | tuple):
        fields = manifest.get("required_match_fields")
    if isinstance(fields, list | tuple):
        for field in fields:
            name = _text(field)
            if name:
                rules.append(
                    {
                        "claim_field": name,
                        "actual_field": name,
                        "label": name,
                        "required": True,
                    }
                )
    return rules


def _manifest_match_field_names(manifest: Mapping[str, Any]) -> list[str]:
    return [rule["label"] for rule in _match_rules(manifest)]


def _field_value(record: Mapping[str, Any], field: str) -> tuple[bool, Any]:
    if not field:
        return False, None
    current: Any = record
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            break
        current = current[part]
    else:
        return True, current

    flattened = _flatten(record)
    for path, value in flattened.items():
        if path.split(".")[-1] == field:
            return True, value
    return False, None


def _flatten(record: Mapping[str, Any], *, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in record.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            out.update(_flatten(value, prefix=path))
        else:
            out[path] = value
    return out


def _values_equal(expected: Any, actual: Any) -> bool:
    expected_decimal = _decimal(expected)
    actual_decimal = _decimal(actual)
    if expected_decimal is not None and actual_decimal is not None:
        return expected_decimal == actual_decimal
    return str(expected).strip().lower() == str(actual).strip().lower()


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _resolve_time(value: Any, record: Mapping[str, Any]) -> datetime | None:
    if value is None:
        for field in ("executed_at", "action_time", "created_at"):
            present, candidate = _field_value(record, field)
            if present:
                parsed = _parse_time(candidate)
                if parsed is not None:
                    return parsed
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("$."):
            present, candidate = _field_value(record, stripped[2:])
            return _parse_time(candidate) if present else None
        if stripped.startswith("{{") and stripped.endswith("}}"):
            inner = stripped[2:-2].strip()
            for prefix in ("action.", "claimed."):
                if inner.startswith(prefix):
                    present, candidate = _field_value(record, inner[len(prefix):])
                    return _parse_time(candidate) if present else None
        parsed = _parse_time(stripped)
        if parsed is not None:
            return parsed
        present, candidate = _field_value(record, stripped)
        return _parse_time(candidate) if present else None
    return _parse_time(value)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _metadata_retryable(metadata: Mapping[str, Any]) -> bool | None:
    raw_retryable = metadata.get("retryable")
    if isinstance(raw_retryable, bool):
        return raw_retryable
    status = metadata.get("http_status")
    try:
        status_int = int(status)
    except (TypeError, ValueError):
        return None
    return status_int >= 500


def _within_open_window(
    action_time: datetime | None,
    window_seconds: int | None,
    checked_at: datetime,
) -> bool:
    if action_time is None or window_seconds is None:
        return False
    return checked_at < action_time + timedelta(seconds=window_seconds)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def canonical_manifest_digest(manifest: Mapping[str, Any]) -> str:
    rendered = json.dumps(
        _as_dict(manifest),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    # Keep this helper local to the pure module for future connector drift tests.
    import hashlib

    return f"sha256:{hashlib.sha256(rendered.encode('utf-8')).hexdigest()}"
