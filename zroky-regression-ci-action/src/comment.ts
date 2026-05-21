/**
 * Post (or update) a PR comment using the GitHub Action context.
 *
 * Uses the built-in `@actions/github` token; requires
 * `permissions: pull-requests: write` in the calling workflow.
 */

import * as core from '@actions/core';
import * as github from '@actions/github';

const COMMENT_MARKER = '<!-- zroky-regression-ci -->';

export async function postOrUpdateComment(body: string): Promise<void> {
  const token = process.env.GITHUB_TOKEN || '';
  if (!token) {
    core.warning('GITHUB_TOKEN not set; skipping PR comment');
    return;
  }

  const octokit = github.getOctokit(token);
  const context = github.context;

  if (!context.payload.pull_request) {
    core.info('Not a pull-request event; skipping PR comment');
    return;
  }

  const { owner, repo } = context.repo;
  const issue_number = context.payload.pull_request.number;

  const wrappedBody = `${COMMENT_MARKER}\n${body}`;

  // Search for an existing comment by marker.
  const { data: comments } = await octokit.rest.issues.listComments({
    owner,
    repo,
    issue_number,
  });

  const existing = comments.find((c: { id: number; body?: string | null }) =>
    (c.body || '').includes(COMMENT_MARKER),
  );

  if (existing) {
    await octokit.rest.issues.updateComment({
      owner,
      repo,
      comment_id: existing.id,
      body: wrappedBody,
    });
    core.info(`Updated existing PR comment ${existing.id}`);
  } else {
    await octokit.rest.issues.createComment({
      owner,
      repo,
      issue_number,
      body: wrappedBody,
    });
    core.info('Created new PR comment');
  }
}
