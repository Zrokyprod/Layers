from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class ActionPackNotFound(ValueError):
    pass


@dataclass(frozen=True)
class ActionContractTemplate:
    contract_key: str
    version: str
    action_type: str
    operation_kind: str
    domain_family: str
    risk_class: str
    connector_family: str
    schema: Mapping[str, Any]
    verification_profile: Mapping[str, Any]


@dataclass(frozen=True)
class ActionPackDefinition:
    id: str
    display_name: str
    summary: str
    primary_runtime_path: str
    recommended_connectors: tuple[str, ...]
    native_tool_families: tuple[str, ...]
    contract_templates: tuple[ActionContractTemplate, ...]
    quickstart_steps: tuple[str, ...] = ()
    dashboard_href: str = "/agents"
