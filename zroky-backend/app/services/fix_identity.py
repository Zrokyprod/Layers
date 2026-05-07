from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.services.privacy import mask_payload

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return mask_payload(parsed) if isinstance(parsed, dict) else {}


def slug(value: str | None, *, fallback: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "-")
    normalized = _SLUG_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-._")
    return normalized or fallback


def normalize_diagnosis_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
    return normalized or None


def normalize_fix_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:128]


def extract_fix_id_from_result(result_payload: Mapping[str, Any], *, diagnosis_id: str) -> str:
    candidates: list[Any] = [result_payload.get("fix_id")]

    root_fix = result_payload.get("fix")
    if isinstance(root_fix, Mapping):
        candidates.append(root_fix.get("fix_id"))

    diagnoses = result_payload.get("diagnoses")
    first_diagnosis: Mapping[str, Any] | None = None
    if isinstance(diagnoses, list) and diagnoses and isinstance(diagnoses[0], Mapping):
        first_diagnosis = diagnoses[0]
        candidates.append(first_diagnosis.get("fix_id"))
        nested_fix = first_diagnosis.get("fix")
        if isinstance(nested_fix, Mapping):
            candidates.append(nested_fix.get("fix_id"))

    for candidate in candidates:
        normalized = normalize_fix_id(candidate)
        if normalized:
            return normalized

    diagnosis_type = None
    for payload in (first_diagnosis, result_payload):
        if not isinstance(payload, Mapping):
            continue
        for key in ("diagnosis_type", "category", "error_code", "failure_category"):
            diagnosis_type = normalize_diagnosis_type(payload.get(key))
            if diagnosis_type:
                break
        if diagnosis_type:
            break

    safe_diagnosis_id = slug(diagnosis_id, fallback="diagnosis")
    if diagnosis_type:
        return f"fix-{diagnosis_type.lower()}-{safe_diagnosis_id}"[:128]
    return f"fix-diagnosis-{safe_diagnosis_id}"[:128]
