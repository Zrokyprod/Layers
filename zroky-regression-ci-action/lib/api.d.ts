/**
 * Thin HTTP client for the Zroky regression-ci API.
 */
export interface ChangedFile {
    path: string;
    hunks?: string;
}
export interface RegressionCIRunRequest {
    git_sha?: string;
    head_sha?: string;
    base_sha?: string;
    repository?: string;
    pull_request_number?: number;
    workflow_run_id?: string;
    workflow_attempt?: number;
    contract_version_ids?: string[];
    pr_body?: string;
    zroky_yaml?: string;
    changed_files: ChangedFile[];
    threshold?: number;
    operator_override?: {
        category: string;
        target?: string;
    };
    target_total_cap?: number;
    sample_window_days?: number;
}
export interface RegressionCIRunResponse {
    run_id: string;
    project_id: string;
    git_sha: string;
    status: string;
    summary_url: string;
    fixture_url?: string;
    run_token?: string;
    contract_version_ids?: string[];
    runner_required?: boolean;
}
export interface RegressionCIRunDetailResponse {
    run_id: string;
    project_id: string;
    git_sha?: string;
    head_sha?: string;
    repository?: string;
    pull_request_number?: number;
    status: string;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    effective_status?: string;
    failed_goldens?: Record<string, unknown>[];
    warn_goldens?: Record<string, unknown>[];
    not_verified_reasons?: string[];
    override?: Record<string, unknown>;
    report?: Record<string, unknown>;
    pr_comment_markdown?: string;
}
export interface RunnerEvidenceRequest {
    candidate_sha: string;
    agent_release: Record<string, unknown>;
    trials: Record<string, unknown>[];
    trace: Record<string, unknown>;
    business_outcome: Record<string, unknown>;
    state_diff: Record<string, unknown>;
    errors: unknown[];
}
export interface RunnerEvidenceResponse {
    run_id: string;
    status: string;
    verdict: string;
    trial_count: number;
    required_trials: number;
    critical_violation_count: number;
    not_verified_reasons?: string[];
}
export interface FixtureBundle {
    schema_version: string;
    run_id: string;
    project_id: string;
    head_sha?: string;
    contract_version_ids: string[];
    contracts: Record<string, unknown>[];
    fixtures: Record<string, unknown>[];
}
export declare class ZrokyApiClient {
    private baseUrl;
    private apiKey;
    private projectId;
    private client;
    constructor(baseUrl: string, apiKey: string, projectId: string);
    dispatchRun(body: RegressionCIRunRequest): Promise<RegressionCIRunResponse>;
    getRun(runId: string): Promise<RegressionCIRunDetailResponse>;
    getFixture(fixtureUrl: string, runToken: string): Promise<FixtureBundle>;
    uploadEvidence(runId: string, runToken: string, body: RunnerEvidenceRequest): Promise<RunnerEvidenceResponse>;
}
