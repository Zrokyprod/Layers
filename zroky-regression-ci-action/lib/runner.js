"use strict";
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
exports.executeRepositoryRunner = executeRepositoryRunner;
exports.parseRunnerEvidence = parseRunnerEvidence;
exports.validateRunnerEvidence = validateRunnerEvidence;
exports.buildRunnerErrorEvidence = buildRunnerErrorEvidence;
const fs = __importStar(require("fs/promises"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
const child_process_1 = require("child_process");
const util_1 = require("util");
const execAsync = (0, util_1.promisify)(child_process_1.exec);
async function executeRepositoryRunner(options) {
    const fixturePath = await writeFixture(options.fixture, options.runId);
    try {
        const result = await execAsync(options.command, {
            cwd: process.cwd(),
            timeout: options.timeoutSeconds * 1000,
            maxBuffer: 10 * 1024 * 1024,
            env: {
                ...process.env,
                ZROKY_RUN_ID: options.runId,
                ZROKY_FIXTURE_PATH: fixturePath,
                ZROKY_HEAD_SHA: options.candidateSha,
                ZROKY_CONTRACT_VERSION_IDS: JSON.stringify(options.contractVersionIds),
            },
        });
        try {
            return parseRunnerEvidence(result.stdout);
        }
        catch (error) {
            return buildRunnerErrorEvidence(options.candidateSha, 'invalid_output', error instanceof Error ? error.message : String(error));
        }
    }
    catch (error) {
        const err = error;
        if (err.stdout) {
            try {
                return parseRunnerEvidence(err.stdout);
            }
            catch {
                // Fall through to structured runner error below.
            }
        }
        return buildRunnerErrorEvidence(options.candidateSha, 'runner_error', err.stderr || err.message || 'runner command failed');
    }
}
function parseRunnerEvidence(stdout) {
    const candidates = [stdout.trim(), ...stdout.split(/\r?\n/).reverse().map((line) => line.trim())];
    for (const candidate of candidates) {
        if (!candidate.startsWith('{')) {
            continue;
        }
        try {
            const parsed = JSON.parse(candidate);
            const error = validateRunnerEvidence(parsed);
            if (error) {
                throw new Error(error);
            }
            return parsed;
        }
        catch {
            continue;
        }
    }
    throw new Error('runner output did not contain valid JSON evidence');
}
function validateRunnerEvidence(value) {
    if (!isRecord(value)) {
        return 'runner evidence must be a JSON object';
    }
    if (typeof value.candidate_sha !== 'string' || !value.candidate_sha.trim()) {
        return 'candidate_sha is required';
    }
    if (!isRecord(value.agent_release)) {
        return 'agent_release is required';
    }
    if (!Array.isArray(value.trials)) {
        return 'trials must be an array';
    }
    if (!isRecord(value.trace)) {
        return 'trace is required';
    }
    if (!isRecord(value.business_outcome)) {
        return 'business_outcome is required';
    }
    if (!isRecord(value.state_diff)) {
        return 'state_diff is required';
    }
    if (!Array.isArray(value.errors)) {
        return 'errors must be an array';
    }
    return null;
}
function buildRunnerErrorEvidence(candidateSha, type, message) {
    return {
        candidate_sha: candidateSha,
        agent_release: {
            agent_name: 'repository-runner',
            environment: 'ci',
        },
        trials: [],
        trace: {},
        business_outcome: {},
        state_diff: {},
        errors: [
            {
                type,
                severity: 'error',
                message,
            },
        ],
    };
}
async function writeFixture(fixture, runId) {
    const baseDir = process.env.RUNNER_TEMP || os.tmpdir();
    const filePath = path.join(baseDir, `zroky-fixture-${runId}.json`);
    await fs.writeFile(filePath, JSON.stringify(fixture, null, 2), 'utf8');
    return filePath;
}
function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
//# sourceMappingURL=runner.js.map