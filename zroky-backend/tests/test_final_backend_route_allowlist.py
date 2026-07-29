from __future__ import annotations

from app.api.router import api_router


def test_final_backend_router_excludes_old_product_surfaces() -> None:
    paths = sorted({getattr(route, "path", "") for route in api_router.routes})

    blocked_prefixes = (
        "/v1/ablation",
        "/v1/analytics/summary",
        "/v1/ask",
        "/v1/contracts",
        "/v1/detectors",
        "/v1/diagnoses",
        "/v1/diagnosis",
        "/v1/digest",
        "/v1/drift",
        "/v1/fix-events",
        "/v1/goldens",
        "/v1/intel",
        "/v1/issues",
        "/v1/judge",
        "/v1/live",
        "/v1/recommendations",
        "/v1/regression-ci",
        "/v1/reliability",
        "/v1/replay",
    )
    violations = [path for path in paths if path.startswith(blocked_prefixes)]

    assert violations == []


def test_final_backend_router_keeps_required_launch_surfaces() -> None:
    paths = sorted({getattr(route, "path", "") for route in api_router.routes})

    required_prefixes = (
        "/v1/action-intents",
        "/v1/action-execution-attempts",
        "/v1/intents",
        "/v1/policy/check",
        "/v1/relay-protocol/read-commands/prepare",
        "/v1/runs",
        "/v1/incidents",
        "/v1/evidence",
        "/v1/outcomes/reconciliation",
        "/v1/assurance-packs",
        "/v1/integrations/system-of-record",
        "/v1/auth",
        "/v1/billing",
        "/v1/projects",
    )
    missing = [
        prefix
        for prefix in required_prefixes
        if not any(path.startswith(prefix) for path in paths)
    ]

    assert missing == []
