import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CallListItem(BaseModel):
    call_id: str
    tenant_id: str
    status: str
    provider: str | None = None
    model: str | None = None
    agent_name: str | None = None
    user_id: str | None = None
    call_type: str | None = None
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: str | None = None
    confidence_reason: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    diagnoses: list[str] = Field(default_factory=list)
    has_blast_radius: bool = False
    created_at: datetime
    updated_at: datetime


class CallListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CallListItem]


class AdjacentCallItem(BaseModel):
    id: str
    model: str | None = None
    status: str


class AdjacentCallsResponse(BaseModel):
    prev: AdjacentCallItem | None = None
    next: AdjacentCallItem | None = None


class CallFeedbackSummary(BaseModel):
    helpful_count: int = 0
    not_helpful_count: int = 0


class CallDetailResponse(BaseModel):
    call: CallListItem
    payload: dict[str, Any]
    cost_audit: dict[str, Any] | None = None
    diagnosis_result: dict[str, Any] | None = None
    feedback_summary: CallFeedbackSummary


class ActivityFeedItemResponse(BaseModel):
    log_id: str
    tenant_id: str
    diagnosis_id: str
    action: str
    actor_subject: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime


class ActivityFeedResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ActivityFeedItemResponse]


class TraceRootFailureResponse(BaseModel):
    category: str | None = None
    root_cause: str | None = None


class TraceTreeNodeResponse(BaseModel):
    call_id: str
    parent_call_id: str | None = None
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    cost_confidence: str | None = None
    status: str
    wasted_cost_usd: float = 0.0
    latency_ms: float | None = None
    error_code: str | None = None
    created_at: datetime
    children: list["TraceTreeNodeResponse"] = Field(default_factory=list)


class CallTraceTreeResponse(BaseModel):
    call_id: str
    trace_id: str | None = None
    root_failure: TraceRootFailureResponse | None = None
    total_downstream_calls: int = 0
    total_wasted_cost_usd: float = 0.0
    root_node: TraceTreeNodeResponse


TraceTreeNodeResponse.model_rebuild()


class TraceListItem(BaseModel):
    trace_id: str
    root_call_id: str
    call_count: int
    agent_count: int
    agents: list[str]
    providers: list[str]
    started_at: str
    last_seen_at: str
    total_cost_usd: float
    has_failure: bool
    root_failure_category: str | None = None


class TraceListResponse(BaseModel):
    window_days: int
    total: int
    multi_agent_count: int
    failed_count: int = 0
    items: list[TraceListItem]


class FixAdoptionSummary(BaseModel):
    viewed_diagnoses: int = 0
    resolved_diagnoses: int = 0
    adoption_rate_percent: float = 0.0
    status_band: Literal["strong", "warning", "critical"]


class FixHealthTrustSummary(BaseModel):
    adoption_rate: float = 0.0
    adoption_rate_delta: float = 0.0
    success_rate: float = 0.0
    success_rate_delta: float = 0.0
    regression_rate: float = 0.0
    regression_rate_delta: float = 0.0
    median_time_to_resolution_hours: float | None = None
    median_time_to_resolution_hours_delta: float | None = None
    average_resolution_confidence: float = 0.0
    average_resolution_confidence_delta: float = 0.0
    major_regressions_count: int = 0
    major_regressions_count_delta: int = 0
    severity_indicator: Literal["stable", "watch", "critical"] = "stable"


class FixFunnelStep(BaseModel):
    state: str
    label: str
    count: int
    conversion_rate: float


class FixTrendPoint(BaseModel):
    day: str
    success_rate: float
    regression_rate: float
    resolved_count: int
    regressed_count: int


class FixDiagnosisPerformanceItem(BaseModel):
    diagnosis_type: str
    fix_tags: list[str] = Field(default_factory=list)
    shown_count: int
    adopted_count: int
    resolved_count: int
    regressed_count: int
    adoption_rate: float
    success_rate: float
    regression_rate: float
    median_resolution_hours: float | None = None


class FixActionQueueItem(BaseModel):
    fix_id: str
    diagnosis_id: str
    status_badge: Literal["stable", "watch", "critical"]
    priority: str
    diagnosis_type: str
    fix_title: str
    current_state: str
    success_status: Literal["unresolved", "resolved", "regressed"]
    resolution_confidence: float | None = None
    resolution_correlation: str | None = None
    attribution_mode: str | None = None
    regression_severity: str | None = None
    risk_level: str | None = None
    blast_radius: str | None = None
    time_open_hours: float
    recommended_next_action: str


class FixMicroInsight(BaseModel):
    message: str
    severity: Literal["stable", "watch", "critical"] = "stable"
    diagnosis_type: str | None = None
    priority_hint: str | None = None
    action_label: str | None = None


class FixAnalyticsResponse(BaseModel):
    generated_at: datetime
    window_days: int
    health: FixHealthTrustSummary
    funnel: list[FixFunnelStep]
    trend: list[FixTrendPoint]
    diagnosis_performance: list[FixDiagnosisPerformanceItem]
    action_queue: list[FixActionQueueItem]
    micro_insight: FixMicroInsight


class FeedbackCategoryVisibility(BaseModel):
    category: str
    feedback_total: int
    thumbs_down_count: int
    thumbs_down_rate_percent: float


class FeedbackLoopVisibility(BaseModel):
    feedback_total: int = 0
    thumbs_down_total: int = 0
    thumbs_down_rate_percent: float = 0.0
    by_category: list[FeedbackCategoryVisibility] = Field(default_factory=list)


class AnalyticsSummaryResponse(BaseModel):
    calls_today: int
    calls_yesterday: int = 0
    cost_today_usd: float
    cost_yesterday_usd: float = 0.0
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14
    open_issues: int
    health_score: float
    fix_adoption: FixAdoptionSummary
    feedback_loop: FeedbackLoopVisibility
    unusual_activity: dict[str, Any] | None = None
    updated_at: datetime


class HealthScoreResponse(BaseModel):
    health_score: float
    status_band: Literal["perfect", "green", "yellow", "red"]
    success_rate: float
    latency_score: float
    cost_anomaly_score: float = Field(
        ...,
        title="Cost Issue Score",
        description=(
            "Compatibility wire field retained as cost_anomaly_score; scores "
            "cost-related issue pressure in the health calculation."
        ),
    )
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14
    open_issues_score: float
    details: dict[str, Any]
    updated_at: datetime


class CostDailyTrendPoint(BaseModel):
    day: str
    total_cost_usd: float
    total_cost_display: float = 0.0
    call_count: int
    failed_cost_usd: float = 0.0
    failed_call_count: int = 0


class CostDailyTrendResponse(BaseModel):
    days: int
    points: list[CostDailyTrendPoint]
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    data_source: str = "postgres"
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14


class CostBreakdownItem(BaseModel):
    key: str
    total_cost_usd: float
    total_cost_display: float = 0.0
    call_count: int
    failed_cost_usd: float = 0.0
    failed_call_count: int = 0


class CostBreakdownResponse(BaseModel):
    days: int
    items: list[CostBreakdownItem]
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14


class ReasoningShareResponse(BaseModel):
    days: int
    total_cost_usd: float
    total_cost_display: float = 0.0
    reasoning_cost_usd: float
    reasoning_cost_display: float = 0.0
    reasoning_share_percent: float
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14


class CacheSavingsPoint(BaseModel):
    day: str
    cache_savings_usd: float
    cache_savings_display: float = 0.0


class CacheSavingsResponse(BaseModel):
    days: int
    total_cache_savings_usd: float
    total_cache_savings_display: float = 0.0
    points: list[CacheSavingsPoint]
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14


class BudgetStatusResponse(BaseModel):
    spent_usd: float
    limit_usd: float | None
    percent_used: float | None
    days_remaining_in_period: int
    forecast_exhaust_in_days: float | None
    status: Literal["ok", "warning", "critical", "no_limit"]
    forecast_risk_level: str
    forecast_recommendation: str


class CostTopCallItem(BaseModel):
    call_id: str
    model: str | None
    provider: str | None
    cost_usd: float
    status: str
    agent_name: str | None
    user_id: str | None = None
    call_type: str | None = None
    error_code: str | None
    cost_confidence: str | None = None
    confidence_reason: str | None = None
    pricing_source: str | None = None
    pricing_age_days: int | None = None
    created_at: datetime


class CostTopCallsResponse(BaseModel):
    window_hours: int
    items: list[CostTopCallItem]


class CostHourlyPoint(BaseModel):
    hour: str
    total_cost_usd: float
    call_count: int
    failed_cost_usd: float = 0.0
    failed_count: int = 0


class CostHourlyResponse(BaseModel):
    hours: int
    points: list[CostHourlyPoint]
    cost_total_usd: float = 0.0
    cost_total_display: float = 0.0
    display_currency: Literal["USD", "INR"] = "USD"
    display_currency_code: Literal["USD", "INR"] = "USD"
    display_currency_symbol: str = "$"
    requested_display_currency: Literal["USD", "INR"] = "USD"
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    display_decimal_places: int = 2
    display_rounding_mode: str = "HALF_UP"
    exchange_rate_decimal_places: int = 8
    pricing_version: str | None = None
    pricing_source: str | None = None
    pricing_last_updated_at: str | None = None
    pricing_age_days: int | None = None
    cost_currency: str = "USD"
    token_unit: str = "tokens"
    cost_confidence: Literal["high", "stale", "degraded"] = "degraded"
    confidence_reason: str | None = None
    cost_baseline_window_days: int = 14


class LoopIncidentItem(BaseModel):
    diagnosis_id: str
    agent_name: str | None = None
    created_at: datetime
    loop_score: float = 0.0
    dominant_pattern: str | None = None
    repeat_count: int = 0
    no_progress: bool = False
    estimated_cost_usd: float = 0.0
    retry_suppression_applied: bool = False


class LoopIncidentsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    window_days: int
    items: list[LoopIncidentItem]


class LoopDayPoint(BaseModel):
    day: str
    count: int


class LoopSummaryResponse(BaseModel):
    window_days: int
    total_loop_count: int
    estimated_waste_usd: float = 0.0
    top_looping_agent: str | None = None
    most_common_pattern: str | None = None
    loop_count_by_day: list[LoopDayPoint] = Field(default_factory=list)


class BudgetConfigUpdateRequest(BaseModel):
    monthly_limit_usd: float | None = Field(default=None, ge=0)
    threshold_percentage: float = Field(default=80.0, ge=1.0, le=100.0)


class AuthTrendPoint(BaseModel):
    hour: str
    count: int


class SavingsSummaryResponse(BaseModel):
    """Aggregate ROI surface — "what Zroky saved you" across a time window.

    Sourced from the legacy `issues` table for the present surface; the
    aggregation logic intentionally lives at the route layer so it can be
    repointed to `anomalies` once the Phase B migration finishes.
    """
    window_days: int
    total_caught_count: int = 0  # number of issues raised in the window
    total_resolved_count: int = 0  # number of issues resolved in the window
    cumulative_wasted_usd: float = 0.0  # sum of blast_radius_usd while open
    cumulative_resolved_blast_usd: float = 0.0  # blast_radius_usd for closed issues
    projected_averted_usd: float = 0.0  # 6h forward projection on resolved issues
    affected_calls: int = 0  # sum of occurrence_count across issues in window
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    updated_at: datetime


class AuthSummaryResponse(BaseModel):
    window_hours: int
    total_auth_failures: int
    open_alert_count: int
    is_ongoing: bool = False
    affected_providers: list[str] = Field(default_factory=list)
    last_failure_at: str | None = None
    first_failure_at: str | None = None
    mean_time_to_acknowledge_minutes: float | None = None
    trend: list[AuthTrendPoint] = Field(default_factory=list)


class BudgetConfigResponse(BaseModel):
    monthly_limit_usd: float | None = None
    threshold_percentage: float
    updated_at: datetime


class AlertItemResponse(BaseModel):
    alert_id: str
    diagnosis_id: str
    category: str
    severity: str
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
    source: str
    title: str
    evidence: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class AlertListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AlertItemResponse]


class AlertChannelTestRequest(BaseModel):
    channel: Literal["email", "slack", "browser", "terminal"]


class AlertChannelTestResponse(BaseModel):
    channel: str
    status: Literal["queued", "sent"]
    message: str


class OnboardingTriggerRequest(BaseModel):
    category: Literal[
        "TOKEN_OVERFLOW",
        "RATE_LIMIT",
        "AUTH_FAILURE",
        "LOOP_DETECTED",
        "COST_SPIKE",
    ] = "TOKEN_OVERFLOW"


class OnboardingTriggerResponse(BaseModel):
    diagnosis_id: str
    status: str
    synthetic: bool = True
    message: str


class PiiPolicyUpdateRequest(BaseModel):
    custom_patterns: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("custom_patterns")
    @classmethod
    def normalize_patterns(cls, value: list[str]) -> list[str]:
        normalized = []
        for item in value:
            if not item or not item.strip():
                continue
            pattern = item.strip()
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid PII pattern: {pattern}") from exc
            normalized.append(pattern)
        return normalized


class PiiPolicyResponse(BaseModel):
    custom_patterns: list[str]
    updated_at: datetime


class PiiDetectorTestRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=512)
    sample_text: str = Field(min_length=1, max_length=4000)


class PiiDetectorTestResponse(BaseModel):
    valid: bool
    match_count: int
    matches: list[str]
    error: str | None = None


class RetentionPolicyUpdateRequest(BaseModel):
    retention_days: int = Field(ge=1, le=3650)


class RetentionPolicyResponse(BaseModel):
    retention_days: int
    updated_at: datetime


class RetentionDataErasureResponse(BaseModel):
    tenant_id: str
    dry_run: bool
    batch_size: int
    deleted_by_table: dict[str, int] = Field(default_factory=dict)
    total_deleted: int
    erased_at: datetime


class NotificationSettingsUpdateRequest(BaseModel):
    email_enabled: bool
    slack_enabled: bool
    teams_enabled: bool = False
    browser_enabled: bool
    terminal_enabled: bool


class NotificationSettingsResponse(BaseModel):
    email_enabled: bool
    slack_enabled: bool
    teams_enabled: bool = False
    browser_enabled: bool
    terminal_enabled: bool
    updated_at: datetime


class EvaluationSettingsUpdateRequest(BaseModel):
    judge_mode: Literal["fast", "standard", "strict"] = "standard"
    default_judge_model: str = Field(default="auto", min_length=1, max_length=120)
    minimum_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    auto_calibration_enabled: bool = True
    record_replay_calibration: bool = True


class EvaluationSettingsResponse(BaseModel):
    judge_mode: Literal["fast", "standard", "strict"]
    default_judge_model: str
    minimum_confidence: float
    auto_calibration_enabled: bool
    record_replay_calibration: bool
    updated_at: datetime


class GithubConnectCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=4096)


class GithubConnectionStatusResponse(BaseModel):
    connected: bool
    github_id: str | None = None
    github_login: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    updated_at: datetime | None = None


class PricingInterviewNote(BaseModel):
    developer_ref: str = Field(min_length=1, max_length=255)
    preferred_model: Literal["tiered", "usage_based", "undecided"] = "undecided"
    fairness_score: float = Field(ge=1.0, le=5.0)
    call_volume_context: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    interviewed_at: datetime


class PricingValidationUpdateRequest(BaseModel):
    selected_launch_model: Literal["tiered", "usage_based", "undecided"] = "undecided"
    rationale: str | None = Field(default=None, max_length=4000)
    migration_path: str | None = Field(default=None, max_length=4000)
    interviews: list[PricingInterviewNote] = Field(default_factory=list, max_length=100)
    lock_pricing_decision: bool = False


class PricingValidationResponse(BaseModel):
    selected_launch_model: Literal["tiered", "usage_based", "undecided"]
    rationale: str | None = None
    migration_path: str | None = None
    interviews: list[PricingInterviewNote] = Field(default_factory=list)
    interview_count: int
    unique_developer_count: int
    required_interviews: int = 5
    missing_interviews: int
    minimum_interviews_met: bool
    pricing_locked: bool
    launch_gate_passed: bool
    blockers: list[str] = Field(default_factory=list)
    locked_at: datetime | None = None
    updated_at: datetime


class RollbackDrillUpdateRequest(BaseModel):
    deploy_revision: str | None = Field(default=None, max_length=128)
    rollback_revision: str | None = Field(default=None, max_length=128)
    deploy_test_passed: bool = False
    rollback_test_passed: bool = False
    failure_simulation_performed: bool = False
    failure_simulation_category: Literal[
        "TOKEN_OVERFLOW",
        "RATE_LIMIT",
        "AUTH_FAILURE",
        "LOOP_DETECTED",
        "COST_SPIKE",
    ] | None = None
    failure_simulation_notes: str | None = Field(default=None, max_length=4000)
    drill_notes: str | None = Field(default=None, max_length=4000)
    status: Literal["not_started", "in_progress", "passed", "failed"] = "not_started"


class RollbackDrillResponse(BaseModel):
    deploy_revision: str | None = None
    rollback_revision: str | None = None
    deploy_test_passed: bool
    rollback_test_passed: bool
    failure_simulation_performed: bool
    failure_simulation_category: str | None = None
    failure_simulation_notes: str | None = None
    drill_notes: str | None = None
    status: Literal["not_started", "in_progress", "passed", "failed"]
    completed_at: datetime | None = None
    updated_at: datetime


class RollbackDrillVerifyRequest(BaseModel):
    phase: Literal["deploy", "rollback"]
    deploy_revision: str | None = Field(default=None, max_length=128)
    rollback_revision: str | None = Field(default=None, max_length=128)


class RollbackDrillVerificationCheck(BaseModel):
    name: Literal["database", "redis"]
    status: Literal["ok", "failed", "skipped"]
    detail: str


class RollbackDrillVerificationResponse(BaseModel):
    phase: Literal["deploy", "rollback"]
    passed: bool
    checks: list[RollbackDrillVerificationCheck] = Field(default_factory=list)
    verified_at: datetime
    rollback_drill: RollbackDrillResponse


class ProviderVerificationItem(BaseModel):
    provider: str
    status: Literal["verified", "unverified", "failed"]
    tracked_call_count: int
    last_checked_at: datetime | None = None
    last_error: str | None = None


class ProviderVerificationListResponse(BaseModel):
    items: list[ProviderVerificationItem]


class ProviderVerificationTestResponse(BaseModel):
    provider: str
    status: Literal["verified", "failed"]
    message: str
    checked_at: datetime


class ExportDiagnosisItem(BaseModel):
    tenant_id: str
    diagnosis_id: str
    status: str
    categories: list[str] = Field(default_factory=list)
    result_json: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ExportCallItem(BaseModel):
    call: CallListItem
    payload: dict[str, Any]
    diagnosis_result: dict[str, Any] | None = None
    feedback_summary: CallFeedbackSummary


class ExportResponse(BaseModel):
    tenant_id: str
    generated_at: datetime
    call_count: int
    diagnosis_count: int
    alert_count: int
    calls: list[ExportCallItem]
    diagnoses: list[ExportDiagnosisItem]
    alerts: list[AlertItemResponse]
