# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""SDK configuration — reads from env vars or explicit init() params."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_API_BASE_URL = "https://api.zroky.com"
_INGEST_ENDPOINT_SUFFIXES = ("/api/v1/ingest", "/v1/ingest", "/ingest")


@dataclass
class SDKConfig:
    api_key: str | None
    project: str | None
    mode: str            # "cloud" | "local"
    mask_pii: bool
    ingest_url: str
    default_agent: str | None
    default_agent_id: str | None
    verbose: bool
    batch_size: int
    flush_interval_seconds: float
    max_queue_size: int  # Max events in memory queue before dropping
    agent_framework: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    prompt_version: str | None = None
    environment: str | None = None
    code_sha: str | None = None
    deployment_id: str | None = None
    model_version: str | None = None
    tool_schema_version: str | None = None
    rag_version: str | None = None
    validate_preflight: bool = False
    validate_preflight_sample_rate: float = 1.0
    preflight_blocking_warning_types: tuple[str, ...] = ()
    enable_offline_buffer: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout_seconds: float = 60.0
    retry_max_retries: int = 2
    retry_base_backoff_seconds: float = 0.5
    retry_max_backoff_seconds: float = 30.0
    fallback_models: tuple[str, ...] = ()
    fallback_max: int = 3
    fallback_adaptive: bool = False
    rate_limits: dict[str, dict[str, int]] = field(default_factory=dict)
    rate_limit_enabled: bool = True
    cache_enabled: bool = True
    cache_default_ttl: float = 3600.0
    cache_max_memory: int = 1000
    cache_db_path: str | None = None
    cache_ttl_overrides: dict[str, float] = field(default_factory=dict)
    budget_enabled: bool = False
    budget_db_path: str | None = None
    budget_default_rate: float = 5.0
    budget_rules: dict[str, dict[str, dict[str, dict[str, Any]]]] = field(default_factory=dict)
    loop_guard_enabled: bool = False
    loop_guard_max_calls_per_trace: int = 50
    loop_guard_max_repeated_outputs: int = 3
    loop_guard_max_cost_per_trace_usd: float = 10.0
    loop_guard_action: str = "raise"
    timeout_enabled: bool = True
    timeout_stream_chunk_seconds: float = 15.0
    default_timeout: float | None = None


def load_config(
    *,
    api_key: str | None = None,
    project: str | None = None,
    mode: str | None = None,
    mask_pii: bool | None = None,
    ingest_url: str | None = None,
    agent_id: str | None = None,
    agent_framework: str | None = None,
    session_id: str | None = None,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
    prompt_version: str | None = None,
    environment: str | None = None,
    code_sha: str | None = None,
    deployment_id: str | None = None,
    model_version: str | None = None,
    tool_schema_version: str | None = None,
    rag_version: str | None = None,
    validate_preflight: bool | None = None,
    validate_preflight_sample_rate: float | None = None,
    preflight_blocking_warning_types: list[str] | tuple[str, ...] | None = None,
    circuit_breaker_failure_threshold: int | None = None,
    circuit_breaker_reset_timeout_seconds: float | None = None,
    retry_max_retries: int | None = None,
    retry_base_backoff_seconds: float | None = None,
    retry_max_backoff_seconds: float | None = None,
    fallback_models: list[str] | tuple[str, ...] | None = None,
    fallback_max: int | None = None,
    fallback_adaptive: bool | None = None,
    rate_limits: dict[str, dict[str, int]] | None = None,
    rate_limit_enabled: bool | None = None,
    cache_enabled: bool | None = None,
    cache_default_ttl: float | None = None,
    cache_max_memory: int | None = None,
    cache_db_path: str | None = None,
    cache_ttl_overrides: dict[str, float] | None = None,
    budget_enabled: bool | None = None,
    budget_db_path: str | None = None,
    budget_default_rate: float | None = None,
    budget_rules: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None,
    loop_guard_enabled: bool | None = None,
    loop_guard_max_calls_per_trace: int | None = None,
    loop_guard_max_repeated_outputs: int | None = None,
    loop_guard_max_cost_per_trace_usd: float | None = None,
    loop_guard_action: str | None = None,
    timeout_enabled: bool | None = None,
    timeout_stream_chunk_seconds: float | None = None,
    default_timeout: float | None = None,
) -> SDKConfig:
    resolved_key = api_key or os.environ.get("ZROKY_API_KEY")
    resolved_project = project or os.environ.get("ZROKY_PROJECT")
    resolved_mode = (mode or os.environ.get("ZROKY_MODE", "cloud")).lower()
    resolved_mask = mask_pii if mask_pii is not None else _truthy(
        os.environ.get("ZROKY_MASK_PII", "true")
    )
    resolved_url = _normalize_ingest_url(
        ingest_url or os.environ.get("ZROKY_INGEST_URL", _DEFAULT_API_BASE_URL)
    )
    default_agent = os.environ.get("ZROKY_AGENT")
    default_agent_id = agent_id or os.environ.get("ZROKY_AGENT_ID")
    verbose = _truthy(os.environ.get("ZROKY_VERBOSE", "false"))
    batch_size = int(os.environ.get("ZROKY_BATCH_SIZE", "10"))
    flush_interval = float(os.environ.get("ZROKY_FLUSH_INTERVAL", "5"))
    max_queue_size = int(os.environ.get("ZROKY_MAX_QUEUE_SIZE", "10000"))
    resolved_agent_framework = agent_framework or os.environ.get("ZROKY_AGENT_FRAMEWORK")
    resolved_session_id = session_id or os.environ.get("ZROKY_SESSION_ID")
    resolved_workflow_id = workflow_id or os.environ.get("ZROKY_WORKFLOW_ID")
    resolved_workflow_name = workflow_name or os.environ.get("ZROKY_WORKFLOW_NAME")
    resolved_prompt_version = prompt_version or os.environ.get("ZROKY_PROMPT_VERSION")
    resolved_environment = environment or os.environ.get("ZROKY_ENVIRONMENT")
    resolved_code_sha = code_sha or os.environ.get("ZROKY_CODE_SHA")
    resolved_deployment_id = deployment_id or os.environ.get("ZROKY_DEPLOYMENT_ID")
    resolved_model_version = model_version or os.environ.get("ZROKY_MODEL_VERSION")
    resolved_tool_schema_version = tool_schema_version or os.environ.get("ZROKY_TOOL_SCHEMA_VERSION")
    resolved_rag_version = rag_version or os.environ.get("ZROKY_RAG_VERSION")
    resolved_validate_preflight = (
        validate_preflight
        if validate_preflight is not None
        else _truthy(os.environ.get("ZROKY_VALIDATE_PREFLIGHT", "false"))
    )
    resolved_validate_preflight_sample_rate = _resolve_preflight_sample_rate(
        explicit_value=validate_preflight_sample_rate,
        env_value=os.environ.get("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "1.0"),
    )
    resolved_preflight_blocking_warning_types = _resolve_string_tuple(
        explicit_value=preflight_blocking_warning_types,
        env_value=os.environ.get("ZROKY_PREFLIGHT_BLOCKING_WARNINGS", ""),
        uppercase=True,
    )
    enable_offline_buffer = _truthy(
        os.environ.get("ZROKY_ENABLE_OFFLINE_BUFFER", "true")
    )
    resolved_circuit_threshold = (
        circuit_breaker_failure_threshold
        if circuit_breaker_failure_threshold is not None
        else int(os.environ.get("ZROKY_CIRCUIT_BREAKER_THRESHOLD", "5"))
    )
    resolved_circuit_timeout = (
        circuit_breaker_reset_timeout_seconds
        if circuit_breaker_reset_timeout_seconds is not None
        else float(os.environ.get("ZROKY_CIRCUIT_BREAKER_TIMEOUT", "60.0"))
    )
    resolved_retry_max = (
        retry_max_retries
        if retry_max_retries is not None
        else int(os.environ.get("ZROKY_RETRY_MAX_RETRIES", "2"))
    )
    resolved_retry_base = (
        retry_base_backoff_seconds
        if retry_base_backoff_seconds is not None
        else float(os.environ.get("ZROKY_RETRY_BASE_BACKOFF", "0.5"))
    )
    resolved_retry_max_backoff = (
        retry_max_backoff_seconds
        if retry_max_backoff_seconds is not None
        else float(os.environ.get("ZROKY_RETRY_MAX_BACKOFF", "30.0"))
    )
    resolved_fallback_models = _resolve_string_tuple(
        explicit_value=fallback_models,
        env_value=os.environ.get("ZROKY_FALLBACK_MODELS", ""),
    )
    resolved_fallback_max = (
        fallback_max
        if fallback_max is not None
        else int(os.environ.get("ZROKY_FALLBACK_MAX", "3"))
    )
    resolved_fallback_adaptive = (
        fallback_adaptive
        if fallback_adaptive is not None
        else _truthy(os.environ.get("ZROKY_FALLBACK_ADAPTIVE", "false"))
    )
    resolved_rate_limits: dict[str, dict[str, int]] = rate_limits or {}
    resolved_rate_limit_enabled = (
        rate_limit_enabled
        if rate_limit_enabled is not None
        else _truthy(os.environ.get("ZROKY_RATE_LIMIT_ENABLED", "true"))
    )
    resolved_cache_enabled = (
        cache_enabled
        if cache_enabled is not None
        else _truthy(os.environ.get("ZROKY_CACHE_ENABLED", "true"))
    )
    resolved_cache_ttl = (
        cache_default_ttl
        if cache_default_ttl is not None
        else float(os.environ.get("ZROKY_CACHE_TTL", "3600"))
    )
    resolved_cache_max_memory = (
        cache_max_memory
        if cache_max_memory is not None
        else int(os.environ.get("ZROKY_CACHE_MAX_MEMORY", "1000"))
    )
    resolved_cache_db_path = cache_db_path or os.environ.get("ZROKY_CACHE_DB_PATH")
    resolved_cache_ttl_overrides: dict[str, float] = cache_ttl_overrides or {}
    resolved_budget_enabled = (
        budget_enabled
        if budget_enabled is not None
        else _truthy(os.environ.get("ZROKY_BUDGET_ENABLED", "false"))
    )
    resolved_budget_db_path = budget_db_path or os.environ.get("ZROKY_BUDGET_DB_PATH")
    resolved_budget_default_rate = (
        budget_default_rate
        if budget_default_rate is not None
        else float(os.environ.get("ZROKY_BUDGET_DEFAULT_RATE", "5.0"))
    )
    resolved_budget_rules: dict[str, dict[str, dict[str, dict[str, Any]]]] = budget_rules or {}
    resolved_loop_guard_enabled = (
        loop_guard_enabled
        if loop_guard_enabled is not None
        else _truthy(os.environ.get("ZROKY_LOOP_GUARD_ENABLED", "false"))
    )
    resolved_loop_guard_max_calls_per_trace = (
        loop_guard_max_calls_per_trace
        if loop_guard_max_calls_per_trace is not None
        else int(os.environ.get("ZROKY_LOOP_GUARD_MAX_CALLS", "50"))
    )
    resolved_loop_guard_max_repeated_outputs = (
        loop_guard_max_repeated_outputs
        if loop_guard_max_repeated_outputs is not None
        else int(os.environ.get("ZROKY_LOOP_GUARD_MAX_REPEATED", "3"))
    )
    resolved_loop_guard_max_cost_per_trace_usd = (
        loop_guard_max_cost_per_trace_usd
        if loop_guard_max_cost_per_trace_usd is not None
        else float(os.environ.get("ZROKY_LOOP_GUARD_MAX_COST", "10.0"))
    )
    resolved_loop_guard_action = (
        loop_guard_action
        if loop_guard_action is not None
        else os.environ.get("ZROKY_LOOP_GUARD_ACTION", "raise")
    )
    resolved_timeout_enabled = (
        timeout_enabled
        if timeout_enabled is not None
        else _truthy(os.environ.get("ZROKY_TIMEOUT_ENABLED", "true"))
    )
    resolved_timeout_stream_chunk_seconds = (
        timeout_stream_chunk_seconds
        if timeout_stream_chunk_seconds is not None
        else float(os.environ.get("ZROKY_TIMEOUT_STREAM_CHUNK_SECONDS", "15.0"))
    )
    _env_default_timeout = os.environ.get("ZROKY_DEFAULT_TIMEOUT")
    resolved_default_timeout = (
        default_timeout
        if default_timeout is not None
        else (float(_env_default_timeout) if _env_default_timeout is not None else None)
    )

    if not 0.0 <= resolved_validate_preflight_sample_rate <= 1.0:
        raise ValueError(
            "ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE must be between 0.0 and 1.0"
        )

    if resolved_mode not in ("cloud", "local"):
        raise ValueError(
            f"ZROKY_MODE must be 'cloud' or 'local', got: '{resolved_mode}'"
        )

    if resolved_mode == "cloud" and not resolved_key:
        import warnings  # noqa: PLC0415
        warnings.warn(
            "[ZROKY] ZROKY_API_KEY not set. Calls will be captured locally only. "
            "Set ZROKY_API_KEY to send data to the cloud dashboard.",
            stacklevel=4,
        )

    return SDKConfig(
        api_key=resolved_key,
        project=resolved_project,
        mode=resolved_mode,
        mask_pii=resolved_mask,
        ingest_url=resolved_url,
        default_agent=default_agent,
        default_agent_id=default_agent_id,
        verbose=verbose,
        batch_size=batch_size,
        flush_interval_seconds=flush_interval,
        max_queue_size=max_queue_size,
        agent_framework=resolved_agent_framework,
        session_id=resolved_session_id,
        workflow_id=resolved_workflow_id,
        workflow_name=resolved_workflow_name,
        prompt_version=resolved_prompt_version,
        environment=resolved_environment,
        code_sha=resolved_code_sha,
        deployment_id=resolved_deployment_id,
        model_version=resolved_model_version,
        tool_schema_version=resolved_tool_schema_version,
        rag_version=resolved_rag_version,
        validate_preflight=resolved_validate_preflight,
        validate_preflight_sample_rate=resolved_validate_preflight_sample_rate,
        preflight_blocking_warning_types=resolved_preflight_blocking_warning_types,
        enable_offline_buffer=enable_offline_buffer,
        circuit_breaker_failure_threshold=resolved_circuit_threshold,
        circuit_breaker_reset_timeout_seconds=resolved_circuit_timeout,
        retry_max_retries=resolved_retry_max,
        retry_base_backoff_seconds=resolved_retry_base,
        retry_max_backoff_seconds=resolved_retry_max_backoff,
        fallback_models=resolved_fallback_models,
        fallback_max=resolved_fallback_max,
        fallback_adaptive=resolved_fallback_adaptive,
        rate_limits=resolved_rate_limits,
        rate_limit_enabled=resolved_rate_limit_enabled,
        cache_enabled=resolved_cache_enabled,
        cache_default_ttl=resolved_cache_ttl,
        cache_max_memory=resolved_cache_max_memory,
        cache_db_path=resolved_cache_db_path,
        cache_ttl_overrides=resolved_cache_ttl_overrides,
        budget_enabled=resolved_budget_enabled,
        budget_db_path=resolved_budget_db_path,
        budget_default_rate=resolved_budget_default_rate,
        budget_rules=resolved_budget_rules,
        loop_guard_enabled=resolved_loop_guard_enabled,
        loop_guard_max_calls_per_trace=resolved_loop_guard_max_calls_per_trace,
        loop_guard_max_repeated_outputs=resolved_loop_guard_max_repeated_outputs,
        loop_guard_max_cost_per_trace_usd=resolved_loop_guard_max_cost_per_trace_usd,
        loop_guard_action=resolved_loop_guard_action,
        timeout_enabled=resolved_timeout_enabled,
        timeout_stream_chunk_seconds=resolved_timeout_stream_chunk_seconds,
        default_timeout=resolved_default_timeout,
    )


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_ingest_url(value: str) -> str:
    """Normalize base URL or full ingest endpoint input into an API base URL."""
    normalized = value.strip().rstrip("/") or _DEFAULT_API_BASE_URL
    for suffix in _INGEST_ENDPOINT_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    return normalized or _DEFAULT_API_BASE_URL


def _resolve_string_tuple(
    *,
    explicit_value: list[str] | tuple[str, ...] | None,
    env_value: str,
    uppercase: bool = False,
) -> tuple[str, ...]:
    values: list[str] = []
    if explicit_value is not None:
        raw_values = explicit_value
    else:
        raw_text = env_value.strip()
        if not raw_text:
            return ()
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            raw_values = tuple(raw_text.split(","))
        else:
            if isinstance(parsed, list):
                raw_values = tuple(str(item) for item in parsed)
            else:
                raw_values = tuple(raw_text.split(","))

    for item in raw_values:
        value = str(item).strip()
        if not value:
            continue
        values.append(value.upper() if uppercase else value)
    return tuple(dict.fromkeys(values))


def _resolve_preflight_sample_rate(*, explicit_value: float | None, env_value: str) -> float:
    if explicit_value is not None:
        try:
            resolved = float(explicit_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "validate_preflight_sample_rate must be a float between 0.0 and 1.0"
            ) from exc
        return resolved

    try:
        return float(env_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE must be a float between 0.0 and 1.0"
        ) from exc
