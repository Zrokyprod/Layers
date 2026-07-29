from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ToolRegistryItemResponse(BaseModel):
    id: str
    kind: Literal["runtime_path", "verification_connector", "native_tool_family"]
    label: str
    description: str
    category: str
    phase: Literal["phase1"] = "phase1"
    implementation_status: Literal["available", "template", "planned"]
    launch_tier: Literal["p0", "p1", "p2"] = "p0"
    supported_action_types: list[str] = Field(default_factory=list)
    recommended_for_action_types: list[str] = Field(default_factory=list)
    requires_customer_credentials: bool = False
    dashboard_href: str | None = None
    backend_capability: str | None = None
    manifest_id: str | None = None
    availability_notes: str | None = None


class ToolRegistryRecommendationResponse(BaseModel):
    action_types: list[str] = Field(default_factory=list)
    runtime_path_ids: list[str] = Field(default_factory=list)
    verification_connector_ids: list[str] = Field(default_factory=list)
    native_tool_family_ids: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ToolRegistryResponse(BaseModel):
    schema_version: str
    project_id: str
    agent_id: str | None = None
    action_type: str | None = None
    runtime_paths: list[ToolRegistryItemResponse]
    verification_connectors: list[ToolRegistryItemResponse]
    native_tool_families: list[ToolRegistryItemResponse]
    recommended: ToolRegistryRecommendationResponse
