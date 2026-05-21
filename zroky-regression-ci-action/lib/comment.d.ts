/**
 * Post (or update) a PR comment using the GitHub Action context.
 *
 * Uses the built-in `@actions/github` token; requires
 * `permissions: pull-requests: write` in the calling workflow.
 */
export declare function postOrUpdateComment(body: string): Promise<void>;
