/**
 * Thin HTTP client for the Zroky regression-ci API.
 */
export interface ChangedFile {
    path: string;
    hunks?: string;
}
export interface RegressionCIRunRequest {
    git_sha: string;
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
}
export interface RegressionCIRunDetailResponse {
    run_id: string;
    project_id: string;
    git_sha?: string;
    status: string;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    report?: Record<string, unknown>;
    pr_comment_markdown?: string;
}
export declare class ZrokyApiClient {
    private baseUrl;
    private apiKey;
    private projectId;
    private client;
    constructor(baseUrl: string, apiKey: string, projectId: string);
    dispatchRun(body: RegressionCIRunRequest): Promise<RegressionCIRunResponse>;
    getRun(runId: string): Promise<RegressionCIRunDetailResponse>;
}
