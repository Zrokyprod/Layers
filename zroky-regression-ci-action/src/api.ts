/**
 * Thin HTTP client for the Zroky regression-ci API.
 */

import { HttpClient, HttpClientResponse } from '@actions/http-client';

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
  operator_override?: { category: string; target?: string };
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
  effective_status?: string;
  failed_goldens?: Record<string, unknown>[];
  warn_goldens?: Record<string, unknown>[];
  not_verified_reasons?: string[];
  override?: Record<string, unknown>;
  report?: Record<string, unknown>;
  pr_comment_markdown?: string;
}

export class ZrokyApiClient {
  private client: HttpClient;

  constructor(
    private baseUrl: string,
    private apiKey: string,
    private projectId: string,
  ) {
    this.client = new HttpClient('zroky-regression-ci-action/v1', [], {
      headers: {
        'X-Api-Key': apiKey,
        'X-Project-Id': projectId,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
    });
  }

  async dispatchRun(body: RegressionCIRunRequest): Promise<RegressionCIRunResponse> {
    const url = `${this.baseUrl}/v1/regression-ci/run`;
    const res = await this.client.postJson<RegressionCIRunResponse>(url, body);
    if (res.statusCode !== 202) {
      throw new Error(
        `Dispatch failed: HTTP ${res.statusCode} — ${JSON.stringify(res.result)}`,
      );
    }
    if (!res.result) {
      throw new Error('Dispatch failed: empty response body');
    }
    return res.result;
  }

  async getRun(runId: string): Promise<RegressionCIRunDetailResponse> {
    const url = `${this.baseUrl}/v1/regression-ci/runs/${encodeURIComponent(runId)}`;
    const res = await this.client.getJson<RegressionCIRunDetailResponse>(url);
    if (res.statusCode !== 200) {
      throw new Error(
        `Poll failed: HTTP ${res.statusCode} — ${JSON.stringify(res.result)}`,
      );
    }
    if (!res.result) {
      throw new Error('Poll failed: empty response body');
    }
    return res.result;
  }
}
