from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "zroky.workflow_assurance_pack.v1"


class AssurancePackObjectType(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(min_length=1, max_length=160)
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class AssurancePackEffect(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    object_type: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1)


class AssurancePackSourceBinding(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    connector_capability: str = Field(min_length=1, max_length=255)
    object_type: str = Field(min_length=1, max_length=160)
    freshness_seconds: int = Field(gt=0)


class AssurancePackRecoveryPlaybook(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    incident_type: str = Field(min_length=1, max_length=160)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowAssurancePack(BaseModel):
    schema_version: str = SCHEMA_VERSION
    workflow_key: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=32)
    intent_schema: dict[str, Any] = Field(default_factory=dict)
    object_types: list[AssurancePackObjectType] = Field(min_length=1)
    effects: list[AssurancePackEffect] = Field(min_length=1)
    source_bindings: list[AssurancePackSourceBinding] = Field(min_length=1)
    recovery_playbooks: list[AssurancePackRecoveryPlaybook] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_pinned(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        return value


def validate_assurance_pack(payload: dict[str, Any]) -> WorkflowAssurancePack:
    return WorkflowAssurancePack.model_validate(payload)
