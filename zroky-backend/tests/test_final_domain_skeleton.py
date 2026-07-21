from __future__ import annotations

import importlib

from app.domain import FINAL_DOMAIN_MODULES


def test_final_domain_modules_are_importable() -> None:
    assert FINAL_DOMAIN_MODULES == (
        "intent",
        "policy",
        "approval",
        "assurance_pack",
        "connector_manifest",
        "observation",
        "outcome_graph",
        "incident",
        "recovery",
        "evidence",
        "tenancy",
    )

    for module_name in FINAL_DOMAIN_MODULES:
        module = importlib.import_module(f"app.domain.{module_name}")
        assert module.DOMAIN_MODULE == module_name
