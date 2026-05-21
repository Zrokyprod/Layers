"""Resolve the active judge mode + latest calibration for a (project, judge).

Used by:
  - Regression-CI gate to decide whether to fail or warn on judge fail.
  - Replay executor to attach `judge_accuracy_on_your_data` + `mode`
    to every verdict response.
  - Public dashboard `/judge` page.

Production constraints:
  - Read-only. Never mutates DB state.
  - Degrades gracefully: any DB failure returns the safe default
    (mode='blocking', accuracy=None) so a calibration outage cannot
    silently turn off regression gates.
  - Sub-millisecond on cache hit; <5ms cache miss with appropriate
    indexes (ix_judge_calibration_runs_project_model_date).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import JudgeCalibrationRun, JudgeModeOverride

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JudgeModeView:
    """Snapshot returned by `resolve_mode()`.

    Attributes
    ----------
    mode
        'blocking' (default) or 'advisory'. Consumers should treat
        anything else as 'blocking' for safety.
    reason
        Why the mode is set this way. None when no override exists
        (defaulted to blocking).
    accuracy
        Latest calibration accuracy on this customer's labeled data
        (0..1). None when no run exists yet — surface as "not yet
        calibrated" in UIs.
    sample_count
        Number of labeled traces in the latest run; useful for
        confidence framing in UIs.
    last_run_date
        ISO date of the most recent calibration run; None when never
        calibrated.
    """

    project_id: str
    judge_model: str
    mode: str
    reason: Optional[str]
    accuracy: Optional[float]
    sample_count: Optional[int]
    last_run_date: Optional[str]

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "judge_model": self.judge_model,
            "mode": self.mode,
            "reason": self.reason,
            "accuracy": self.accuracy,
            "sample_count": self.sample_count,
            "last_run_date": self.last_run_date,
        }


_BLOCKING_DEFAULT = "blocking"


def _safe_default(project_id: str, judge_model: str) -> JudgeModeView:
    return JudgeModeView(
        project_id=project_id,
        judge_model=judge_model,
        mode=_BLOCKING_DEFAULT,
        reason=None,
        accuracy=None,
        sample_count=None,
        last_run_date=None,
    )


def _latest_run(
    db: Session, *, project_id: str, judge_model: str
) -> JudgeCalibrationRun | None:
    return db.execute(
        select(JudgeCalibrationRun)
        .where(
            JudgeCalibrationRun.project_id == project_id,
            JudgeCalibrationRun.judge_model == judge_model,
            JudgeCalibrationRun.status == "complete",
        )
        .order_by(desc(JudgeCalibrationRun.run_date))
        .limit(1)
    ).scalar_one_or_none()


def _override(
    db: Session, *, project_id: str, judge_model: str
) -> JudgeModeOverride | None:
    return db.execute(
        select(JudgeModeOverride).where(
            JudgeModeOverride.project_id == project_id,
            JudgeModeOverride.judge_model == judge_model,
        )
    ).scalar_one_or_none()


def resolve_mode(
    db: Session, *, project_id: str, judge_model: str
) -> JudgeModeView:
    """Return the current mode view. Never raises.

    On any DB error, returns the safe default (blocking, no calibration
    visible) and logs at WARNING. The caller should always trust this
    function's return value as authoritative.
    """
    pid = (project_id or "").strip()
    model = (judge_model or "").strip()
    if not pid or not model:
        return _safe_default(pid, model)

    try:
        override = _override(db, project_id=pid, judge_model=model)
        latest = _latest_run(db, project_id=pid, judge_model=model)
    except Exception:  # noqa: BLE001
        logger.warning(
            "judge_mode_resolver: db read failed; defaulting to blocking",
            exc_info=True,
        )
        return _safe_default(pid, model)

    mode = override.mode if override is not None else _BLOCKING_DEFAULT
    reason = override.reason if override is not None else None
    accuracy = float(latest.accuracy) if latest is not None else None
    sample_count = int(latest.sample_count) if latest is not None else None
    last_run_date = latest.run_date.isoformat() if latest is not None else None

    if mode not in {"blocking", "advisory"}:
        # Defensive — only the two known modes are honored downstream.
        mode = _BLOCKING_DEFAULT

    return JudgeModeView(
        project_id=pid,
        judge_model=model,
        mode=mode,
        reason=reason,
        accuracy=accuracy,
        sample_count=sample_count,
        last_run_date=last_run_date,
    )


__all__ = ["JudgeModeView", "resolve_mode"]
