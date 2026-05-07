from typing import Any

from pydantic import BaseModel, Field, model_validator


class IngestEvent(BaseModel):
    call_id: str = Field(min_length=1, max_length=64)
    event_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    provider: str = Field(default="unknown", min_length=1, max_length=120)
    model: str = Field(default="unknown", min_length=1, max_length=120)
    call_type: str = Field(default="chat", min_length=1, max_length=32)
    status: str = Field(default="completed", min_length=1, max_length=32)

    latency_ms: float | None = Field(default=None, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    estimated_prompt_tokens: int | None = Field(default=None, ge=0)
    model_context_limit: int | None = Field(default=None, ge=1)
    model_context_limit_source: str | None = Field(default=None, max_length=64)
    model_context_limit_source_detail: str | None = Field(default=None, max_length=128)
    model_context_limit_confidence: float | None = Field(default=None, ge=0, le=1)
    model_context_limit_catalog_version: str | None = Field(default=None, max_length=64)
    model_context_limit_catalog_updated_at: str | None = Field(default=None, max_length=32)
    model_context_limit_catalog_stale: bool | None = None
    model_context_limit_catalog_stale_after_days: int | None = Field(default=None, ge=1)
    token_estimator_version: str | None = Field(default=None, max_length=64)
    token_rules_version: str | None = Field(default=None, max_length=64)
    completion_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    cache_creation_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    actual_cost_usd: float | None = Field(default=None, ge=0)
    budget_remaining_usd: float | None = Field(default=None, ge=0)
    budget_action_taken: str | None = Field(default=None, max_length=64)
    loop_action_taken: str | None = Field(default=None, max_length=64)
    loop_call_count: int = Field(default=0, ge=0)
    loop_cumulative_cost_usd: float | None = Field(default=None, ge=0)
    exchange_rate_usd_to_inr: float | None = Field(default=None, gt=0)
    exchange_rate_timestamp: float | str | None = None
    exchange_rate_source: str | None = Field(default=None, max_length=64)

    tool_definitions: list[dict[str, Any]] | None = None
    tool_calls_made: list[dict[str, Any]] | None = None
    normalized_output: str | None = Field(default=None, max_length=4000)
    output_content: str | None = Field(default=None, max_length=4000)
    output_fingerprint: str | None = Field(default=None, max_length=64)
    tool_lifecycle_summary: list[dict[str, Any]] | None = None
    retry_metadata: dict[str, Any] | None = None
    cache_hit: bool = False
    timeout_triggered: bool = False
    resolved_model: str | None = Field(default=None, max_length=120)
    fallback_chain: list[str] | None = None
    fallback_attempts: int = Field(default=0, ge=0)
    circuit_open_models: list[str] | None = None

    trace_id: str | None = Field(default=None, max_length=128)
    parent_call_id: str | None = Field(default=None, max_length=128)
    agent_name: str | None = Field(default=None, max_length=255)
    prompt_fingerprint: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=255)
    is_synthetic: bool = False
    is_production: bool | None = None
    environment: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] | None = None

    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=4000)
    failure_reason: dict[str, Any] | None = None
    created_at: float | str | None = None

    @model_validator(mode="after")
    def normalize_strings(self) -> "IngestEvent":
        self.call_id = self.call_id.strip()
        self.event_id = self.event_id.strip() if self.event_id else None
        self.request_id = self.request_id.strip() if self.request_id else None
        self.provider = self.provider.strip() or "unknown"
        self.model = self.model.strip() or "unknown"
        self.call_type = self.call_type.strip() or "chat"
        self.status = self.status.strip() or "completed"
        return self


class IngestBatchRequest(BaseModel):
    events: list[IngestEvent] = Field(min_length=1, max_length=100)


class IngestBatchResponse(BaseModel):
    accepted: int
    queued: int
    duplicates: int
    enqueue_failed: int
