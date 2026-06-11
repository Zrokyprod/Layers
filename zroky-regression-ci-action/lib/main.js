"use strict";
/**
 * GitHub Action entry point for Zroky Regression CI.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const core = __importStar(require("@actions/core"));
const github = __importStar(require("@actions/github"));
const api_1 = require("./api");
const poll_1 = require("./poll");
const comment_1 = require("./comment");
async function run() {
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
        const failOnRegression = core.getBooleanInput('fail_on_regression');
        const failOnNotVerified = core.getBooleanInput('fail_on_not_verified');
        // ── derive PR metadata ────────────────────────────────────────────────
        const ctx = github.context;
        const payload = ctx.payload;
        const pr = payload.pull_request;
        if (!pr) {
            throw new Error('This action must be triggered by a pull_request event.');
        }
        const gitSha = pr.head.sha;
        const prBody = pr.body || '';
        // Build changed-files list from the payload (Action must run after checkout).
        const changedFiles = [];
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
                        changedFiles.push(...parsed.map((p) => typeof p === 'string' ? { path: p } : { path: String(p.path || ''), hunks: String(p.hunks || '') }));
                    }
                }
                catch {
                    core.warning('ZROKY_CHANGED_FILES_JSON is not valid JSON; ignoring');
                }
            }
        }
        // ── dispatch ──────────────────────────────────────────────────────────
        const client = new api_1.ZrokyApiClient(baseUrl, apiKey, projectId);
        const dispatch = await client.dispatchRun({
            git_sha: gitSha,
            pr_body: prBody,
            changed_files: changedFiles,
            threshold,
            sample_window_days: sampleWindowDays,
        });
        core.info(`Dispatched regression-ci run ${dispatch.run_id} for ${gitSha}`);
        core.setOutput('run_id', dispatch.run_id);
        // ── poll ──────────────────────────────────────────────────────────────
        const result = await (0, poll_1.pollUntilTerminal)(client, dispatch.run_id, {
            intervalSeconds: pollInterval,
            timeoutSeconds: timeout,
        });
        const detail = result.detail;
        core.info(`Run ${detail.run_id} finished in ${result.elapsedMs}ms ` +
            `after ${result.pollCount} poll(s) with status=${detail.status}`);
        core.setOutput('status', detail.status);
        core.setOutput('regression_rate', String(detail.report?.regression_rate ?? ''));
        core.setOutput('pr_comment_markdown', detail.pr_comment_markdown || '');
        // ── PR comment ────────────────────────────────────────────────────────
        if (postComment && detail.pr_comment_markdown) {
            await (0, comment_1.postOrUpdateComment)(detail.pr_comment_markdown);
        }
        // ── fail the check? ───────────────────────────────────────────────────
        if (detail.status === 'error') {
            core.setFailed('Regression CI run encountered an error. See dashboard for details.');
            return;
        }
        if (failOnNotVerified && detail.status === 'not_verified') {
            core.setFailed('Regression CI could not prove safety with trusted Goldens. ' +
                'See the PR comment or dashboard for missing proof.');
            return;
        }
        if (failOnRegression && detail.status === 'fail') {
            const rate = detail.report?.regression_rate ?? 'unknown';
            core.setFailed(`Regression CI detected regressions (rate=${rate}). ` +
                `See the PR comment or dashboard for details.`);
            return;
        }
        if (detail.status === 'warn') {
            core.warning('Regression CI produced warning-only Golden evidence.');
            return;
        }
        core.info('Regression CI passed — no regressions detected.');
    }
    catch (error) {
        if (error instanceof Error) {
            core.setFailed(error.message);
        }
        else {
            core.setFailed(String(error));
        }
    }
}
run();
//# sourceMappingURL=main.js.map