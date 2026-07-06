from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionContractRegisterRequest(BaseModel):
    contract_key: str = Field(min_length=3, max_length=160)
    version: str = Field(min_length=1, max_length=32)
    action_type: str = Field(min_length=3, max_length=160)
    operation_kind: str = Field(min_length=3, max_length=32)
    domain_family: str = Field(min_length=3, max_length=64)
    schema_: dict[str, Any] = Field(alias="schema")
    risk_class: str = Field(default="R2", max_length=8)
    verification_profile: dict[str, Any] | None = None
    connector_family: str | None = Field(default=None, max_length=80)


class ActionContractResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    project_id: str
    contract_key: str
    version: str
    contract_version: str
    action_type: str
    operation_kind: str
    domain_family: str
    schema_digest: str
    schema_: dict[str, Any] = Field(alias="schema")
    risk_class: str
    verification_profile: dict[str, Any]
    connector_family: str | None
    status: str
    created_at: datetime


class ActionIntentCreateRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=36)
    contract_version: str = Field(min_length=5, max_length=200)
    action_type: str = Field(min_length=3, max_length=160)
    operation_kind: str = Field(min_length=3, max_length=32)
    environment: str = Field(default="production", max_length=64)
    principal: dict[str, Any] = Field(default_factory=dict)
    actor_chain: list[dict[str, Any]] = Field(default_factory=list)
    purpose: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution_request: dict[str, Any] | None = None
    verification_profile: str | None = Field(default=None, max_length=160)
    deadline: datetime | None = None
    trace_context: dict[str, Any] | None = None


class ActionIntentAgentProfileResponse(BaseModel):
    id: str
    display_name: str
    slug: str
    runtime_path: str
    environment: str | None


class ActionIntentResponse(BaseModel):
    action_id: str
    project_id: str
    agent_id: str | None
    agent_profile: ActionIntentAgentProfileResponse | None
    contract_version: str
    action_type: str
    operation_kind: str
    environment: str
    status: str
    proof_status: str
    receipt_status: str
    idempotency_key: str
    intent_digest: str
    canonical_intent: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None
    authorized_at: datetime | None
    runtime_policy_decision_id: str | None
    deadline: datetime | None
    status_url: str


class ActionIntentDecisionRequest(BaseModel):
    approval_id: str | None = Field(default=None, max_length=36)


class ActionIntentDecisionResponse(ActionIntentResponse):
    allowed: bool
    requires_approval: bool
    reasons: list[str] = Field(default_factory=list)


class ActionIntentListResponse(BaseModel):
    items: list[ActionIntentResponse]
    total_in_page: int
    limit: int
    offset: int


class ActionRunnerRegisterRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    runner_type: str = Field(default="customer_hosted", max_length=32)
    environment: str = Field(default="production", max_length=64)
    supported_operation_kinds: list[str] = Field(default_factory=list)
    credential_scope: dict[str, Any] = Field(default_factory=dict)
    capability_version: str | None = Field(default=None, max_length=64)


class ActionRunnerHeartbeatRequest(BaseModel):
    status: str = Field(default="online", max_length=32)
    heartbeat_payload: dict[str, Any] = Field(default_factory=dict)
    supported_operation_kinds: list[str] | None = None
    capability_version: str | None = Field(default=None, max_length=64)


class ActionRunnerClaimRequest(BaseModel):
    runner_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionRunnerResponse(BaseModel):
    runner_id: str
    project_id: str
    name: str
    runner_type: str
    environment: str
    status: str
    supported_operation_kinds: list[str]
    credential_scope: dict[str, Any]
    heartbeat_payload: dict[str, Any]
    capability_version: str | None
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionRunnerListResponse(BaseModel):
    items: list[ActionRunnerResponse]


class ActionExecutionAdapterContractResponse(BaseModel):
    schema_version: str
    adapter: str
    display_name: str
    operation_kinds: list[str]
    operations: list[str]
    required_target_fields: list[str]
    required_argument_fields: list[str]
    required_result_fields: list[str]
    verification_connector: str
    credential_boundary: str
    protected_credential_returned: bool


class ActionExecutionAdapterListResponse(BaseModel):
    items: list[ActionExecutionAdapterContractResponse]


class ActionExecutionAttemptCreateRequest(BaseModel):
    runner_id: str = Field(min_length=36, max_length=36)
    credential_ref: str = Field(min_length=12, max_length=512)
    execution_plan: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionDispatchRequest(BaseModel):
    dispatch_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionStartRequest(BaseModel):
    runner_metadata: dict[str, Any] = Field(default_factory=dict)


class ActionExecutionFinishRequest(BaseModel):
    final_status: str = Field(max_length=32)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = Field(default=None, max_length=2000)


class ActionExecutionAttemptResponse(BaseModel):
    attempt_id: str
    project_id: str
    action_id: str
    runner_id: str
    attempt_number: int
    status: str
    idempotency_key: str
    credential_ref: str
    plan_digest: str
    execution_plan: dict[str, Any]
    result_summary: dict[str, Any]
    error_message: str | None
    protected_credential_returned: bool
    requested_by_subject: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionExecutionAttemptListResponse(BaseModel):
    items: list[ActionExecutionAttemptResponse]


class ActionTimelineEventResponse(BaseModel):
    event_id: str
    action_id: str
    project_id: str
    event_type: str
    event_digest: str
    actor: str | None
    payload: dict[str, Any]
    created_at: datetime


class ActionTimelineResponse(BaseModel):
    items: list[ActionTimelineEventResponse]


class ActionReceiptResponse(BaseModel):
    receipt_id: str
    project_id: str
    action_id: str
    receipt_digest: str
    evidence_hash: str | None
    signature_algorithm: str
    signature: str
    signing_key_id: str
    signature_valid: bool
    signed_payload: str
    generated_at: datetime
    receipt: dict[str, Any]


class ActionPackContractTemplateResponse(BaseModel):
    contract_key: str
    version: str
    contract_version: str
    action_type: str
    operation_kind: str
    domain_family: str
    risk_class: str
    connector_family: str
    schema_: dict[str, Any] = Field(alias="schema")
    verification_profile: dict[str, Any]


class ActionPackResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    display_name: str
    summary: str
    primary_runtime_path: str
    recommended_connectors: list[str]
    native_tool_families: list[str]
    quickstart_steps: list[str] = Field(default_factory=list)
    dashboard_href: str
    contract_templates: list[ActionPackContractTemplateResponse]


class ActionPackListResponse(BaseModel):
    items: list[ActionPackResponse]


class ActionPackInstallResultResponse(BaseModel):
    contract: ActionContractResponse
    created: bool


class ActionPackInstallResponse(BaseModel):
    pack: ActionPackResponse
    installed_contracts: list[ActionPackInstallResultResponse]
