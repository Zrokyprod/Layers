"use strict";
/**
 * Thin HTTP client for the Zroky regression-ci API.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ZrokyApiClient = void 0;
const http_client_1 = require("@actions/http-client");
class ZrokyApiClient {
    baseUrl;
    apiKey;
    projectId;
    client;
    constructor(baseUrl, apiKey, projectId) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.projectId = projectId;
        this.client = new http_client_1.HttpClient('zroky-regression-ci-action/v1', [], {
            headers: {
                'X-Api-Key': apiKey,
                'X-Project-Id': projectId,
                'Content-Type': 'application/json',
                Accept: 'application/json',
            },
        });
    }
    async dispatchRun(body) {
        const url = `${this.baseUrl}/v1/regression-ci/run`;
        const res = await this.client.postJson(url, body);
        if (res.statusCode !== 202) {
            throw new Error(`Dispatch failed: HTTP ${res.statusCode} — ${JSON.stringify(res.result)}`);
        }
        if (!res.result) {
            throw new Error('Dispatch failed: empty response body');
        }
        return res.result;
    }
    async getRun(runId) {
        const url = `${this.baseUrl}/v1/regression-ci/runs/${encodeURIComponent(runId)}`;
        const res = await this.client.getJson(url);
        if (res.statusCode !== 200) {
            throw new Error(`Poll failed: HTTP ${res.statusCode} — ${JSON.stringify(res.result)}`);
        }
        if (!res.result) {
            throw new Error('Poll failed: empty response body');
        }
        return res.result;
    }
}
exports.ZrokyApiClient = ZrokyApiClient;
//# sourceMappingURL=api.js.map