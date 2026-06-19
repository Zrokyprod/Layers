/**
 * GitHub Action entry point for Zroky Regression CI.
 */

import * as core from '@actions/core';
import * as github from '@actions/github';
import { ZrokyApiClient, ChangedFile } from './api';
import { pollUntilTerminal } from './poll';
import { postOrUpdateComment } from './comment';
import { loadZrokyConfig } from './config';
import { buildRunnerErrorEvidence, executeRepositoryRunner } from './runner';
import { failClosedMessage } from './fail-closed';

async function run(): Promise<void> {
  try {
    // ── inputs ────────────────────────────────────────────────────────────
    const apiKey = core.getInput('api_key', { required: true });
    const projectId = core.getInput('project_id', { required: true });
    const baseUrl = core.getInput('base_url') || 'https://api.zroky.com';
    const threshold = parseFloat(core.getInput('threshold') || '0.02');
    const sampleWindowDays = parseInt(core.getInput('sample_window_days') || '30', 10);
    const pollInterval = parseInt(core.getInput('poll_interval_seconds') || '5', 10);
    const timeout = parseInt(core.getInput('timeout_seconds') || '300', 10);
    const postComment = core.getBooleanInput('post_pr_comment');
    const configPath = core.getInput('config_path') || 'zroky.yaml';
    const zrokyConfig = await loadZrokyConfig(configPath);

    // ── derive PR metadata ────────────────────────────────────────────────
    const ctx = github.context;
    const payload = ctx.payload;
    const pr = payload.pull_request;
    if (!pr) {
      throw new Error('This action must be triggered by a pull_request event.');
    }

    const gitSha: string = pr.head.sha;
    const baseSha: string = pr.base.sha;
    const prBody: string = pr.body || '';
    const repository = `${ctx.repo.owner}/${ctx.repo.repo}`;
    const workflowAttempt = parseInt(process.env.GITHUB_RUN_ATTEMPT || '1', 10);

    // Build changed-files list from the payload (Action must run after checkout).
    const changedFiles: ChangedFile[] = [];
    // GitHub does not include file-level diff hunks in the pull_request payload.
    // We send the paths so the server can auto-detect the blast radius.
    if (payload.pull_request && Array.isArray(payload.pull_request.changed_files)) {
      // Note: GitHub's payload only gives a *count*, not the list.
      // A real workflow typically runs `git diff` in a prior step and
      // passes the list via an input.  We accept an optional env var fallback.
      const raw = process.env.ZROKY_CHANGED_FILES_JSON;
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            changedFiles.push(...parsed.map((p: unknown) =>
              typeof p === 'string' ? { path: p } : { path: String((p as any).path || ''), hunks: String((p as any).hunks || '') },
            ));
          }
        } catch {
          core.warning('ZROKY_CHANGED_FILES_JSON is not valid JSON; ignoring');
        }
      }
    }

    // ── dispatch ──────────────────────────────────────────────────────────
    const client = new ZrokyApiClient(baseUrl, apiKey, projectId);
    const dispatch = await client.dispatchRun({
      git_sha: gitSha,
      head_sha: gitSha,
      base_sha: baseSha,
      repository,
      pull_request_number: pr.number,
      workflow_run_id: String(ctx.runId),
      workflow_attempt: Number.isFinite(workflowAttempt) ? workflowAttempt : 1,
      pr_body: prBody,
      zroky_yaml: zrokyConfig.raw,
      contract_version_ids: contractVersionIdsFromConfig(zrokyConfig.contracts?.include || []),
      changed_files: changedFiles,
      threshold,
      sample_window_days: sampleWindowDays,
    });

    core.info(`Dispatched regression-ci run ${dispatch.run_id} for ${gitSha}`);
    core.setOutput('run_id', dispatch.run_id);

    if (dispatch.runner_required) {
      if (!dispatch.fixture_url || !dispatch.run_token) {
        throw new Error('Repository replay was requested but fixture_url or run_token was missing.');
      }
      const fixture = await client.getFixture(dispatch.fixture_url, dispatch.run_token);
      const runnerCommand = zrokyConfig.runner?.command;
      if (!runnerCommand) {
        await client.uploadEvidence(
          dispatch.run_id,
          dispatch.run_token,
          buildRunnerErrorEvidence(
            gitSha,
            'setup_error',
            'runner.command is required in zroky.yaml when repository replay is active',
          ),
        );
      } else {
        const evidence = await executeRepositoryRunner({
          command: runnerCommand,
          timeoutSeconds: zrokyConfig.runner?.timeoutSeconds || timeout,
          fixture,
          runId: dispatch.run_id,
          candidateSha: gitSha,
          contractVersionIds: dispatch.contract_version_ids || [],
        });
        const evidenceResult = await client.uploadEvidence(dispatch.run_id, dispatch.run_token, evidence);
        core.info(
          `Uploaded repository replay evidence: verdict=${evidenceResult.verdict}, ` +
            `trials=${evidenceResult.trial_count}/${evidenceResult.required_trials}`,
        );
      }
    }

    // ── poll ──────────────────────────────────────────────────────────────
    const result = await pollUntilTerminal(client, dispatch.run_id, {
      intervalSeconds: pollInterval,
      timeoutSeconds: timeout,
    });

    const detail = result.detail;
    core.info(
      `Run ${detail.run_id} finished in ${result.elapsedMs}ms ` +
        `after ${result.pollCount} poll(s) with status=${detail.status}`,
    );

    core.setOutput('status', detail.status);
    core.setOutput('regression_rate', String(detail.report?.regression_rate ?? ''));
    core.setOutput('pr_comment_markdown', detail.pr_comment_markdown || '');

    // ── PR comment ────────────────────────────────────────────────────────
    if (postComment && detail.pr_comment_markdown) {
      await postOrUpdateComment(detail.pr_comment_markdown);
    }

    // ── fail the check? ───────────────────────────────────────────────────
    const failureMessage = failClosedMessage(detail);
    if (failureMessage) {
      core.setFailed(failureMessage);
      return;
    }

    core.info('Regression CI passed — no regressions detected.');
  } catch (error) {
    if (error instanceof Error) {
      core.setFailed(error.message);
    } else {
      core.setFailed(String(error));
    }
  }
}

function contractVersionIdsFromConfig(include: string[]): string[] {
  return include.filter((item) => /^[0-9a-fA-F-]{32,36}$/.test(item));
}

run();
