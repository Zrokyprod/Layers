"use strict";
/**
 * Post (or update) a PR comment using the GitHub Action context.
 *
 * Uses the built-in `@actions/github` token; requires
 * `permissions: pull-requests: write` in the calling workflow.
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
exports.postOrUpdateComment = postOrUpdateComment;
const core = __importStar(require("@actions/core"));
const github = __importStar(require("@actions/github"));
const COMMENT_MARKER = '<!-- zroky-regression-ci -->';
async function postOrUpdateComment(body) {
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
    const existing = comments.find((c) => (c.body || '').includes(COMMENT_MARKER));
    if (existing) {
        await octokit.rest.issues.updateComment({
            owner,
            repo,
            comment_id: existing.id,
            body: wrappedBody,
        });
        core.info(`Updated existing PR comment ${existing.id}`);
    }
    else {
        await octokit.rest.issues.createComment({
            owner,
            repo,
            issue_number,
            body: wrappedBody,
        });
        core.info('Created new PR comment');
    }
}
//# sourceMappingURL=comment.js.map