"""
Provider Drift Watch (PDW) — Wedge 2.

Public service that runs a deterministic prompt suite against major LLMs daily
and detects silent provider-side behavior shifts via z-score-based drift
detection on both judge pass-rates and semantic embedding cosines.

Layered architecture (see ZROKY-TECHNICAL-PLAN-V2 Wedge 2):

    Layer 1  DB models                  (app/db/models.py — ProviderDrift*)
    Layer 2  Prompt suite + registry    (this package: prompt_suite, registry)
    Layer 3  Probe runner               (runner.py)
    Layer 4  Drift detector             (drift_detector.py)
    Layer 5  Aggregator                 (aggregator.py)
    Layer 6  Scheduler integration      (app/worker/tasks.py — Celery beat)
    Layer 7  Public API + RSS feed      (app/api/routes/provider_drift_public.py)
    Layer 8  Dashboard /drift page      (zroky-dashboard/src/app/drift)

Public re-exports below give external callers a single, stable import
surface (`from app.services.provider_drift import ...`).
"""
from __future__ import annotations

from app.services.provider_drift.categories import (
    CATEGORIES,
    VALID_CATEGORIES,
    Severity,
)
from app.services.provider_drift.models import (
    DriftAlertSpec,
    DriftMetric,
    ModelSpec,
    ProbeOutcome,
    ProbeResult,
    PromptSpec,
)
from app.services.provider_drift.prompt_suite import (
    PROMPT_SUITE_VERSION,
    load_prompt_suite,
    sync_prompts_to_db,
)
from app.services.provider_drift.registry import (
    MODEL_REGISTRY_VERSION,
    load_model_registry,
    sync_models_to_db,
)

__all__ = [
    "CATEGORIES",
    "VALID_CATEGORIES",
    "Severity",
    "DriftAlertSpec",
    "DriftMetric",
    "ModelSpec",
    "ProbeOutcome",
    "ProbeResult",
    "PromptSpec",
    "PROMPT_SUITE_VERSION",
    "load_prompt_suite",
    "sync_prompts_to_db",
    "MODEL_REGISTRY_VERSION",
    "load_model_registry",
    "sync_models_to_db",
]
