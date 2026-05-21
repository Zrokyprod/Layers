"""
Shared pure utility functions used across fix_generator, strategies/, verify, and pr.
No I/O — no imports from other app.services modules except privacy.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.privacy import mask_text

_BRANCH_SANITIZE_RE = re.compile(r"[^a-z0-9._/-]+")


def _as_text(value: Any, *, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return mask_text(value.strip()) or fallback
    try:
        text = mask_text(str(value).strip())
    except Exception:
        return fallback
    return text or fallback


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        result: list[str] = []
        for item in value:
            text = _as_text(item)
            if text and text not in result:
                result.append(text)
        return result
    text = _as_text(value)
    return [text] if text else []


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clean_snippet(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    masked = mask_text(value.strip())
    return masked if masked is not None else ""


def _normalize_diagnosis_type(value: str) -> str:
    normalized = _as_text(value, fallback="UNKNOWN").upper().replace("-", "_").replace(" ", "_")
    return normalized or "UNKNOWN"


def _slug(value: str, *, fallback: str) -> str:
    normalized = _as_text(value).lower().replace(" ", "-")
    normalized = _BRANCH_SANITIZE_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-./")
    return normalized or fallback
