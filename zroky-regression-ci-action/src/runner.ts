import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import { FixtureBundle, RunnerEvidenceRequest } from './api';

const execAsync = promisify(exec);

export interface ExecuteRunnerOptions {
  command: string;
  timeoutSeconds: number;
  fixture: FixtureBundle;
  runId: string;
  candidateSha: string;
  contractVersionIds: string[];
}

export async function executeRepositoryRunner(
  options: ExecuteRunnerOptions,
): Promise<RunnerEvidenceRequest> {
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
    } catch (error) {
      return buildRunnerErrorEvidence(
        options.candidateSha,
        'invalid_output',
        error instanceof Error ? error.message : String(error),
      );
    }
  } catch (error) {
    const err = error as NodeJS.ErrnoException & { stdout?: string; stderr?: string };
    if (err.stdout) {
      try {
        return parseRunnerEvidence(err.stdout);
      } catch {
        // Fall through to structured runner error below.
      }
    }
    return buildRunnerErrorEvidence(
      options.candidateSha,
      'runner_error',
      err.stderr || err.message || 'runner command failed',
    );
  }
}

export function parseRunnerEvidence(stdout: string): RunnerEvidenceRequest {
  const candidates = [stdout.trim(), ...stdout.split(/\r?\n/).reverse().map((line) => line.trim())];
  for (const candidate of candidates) {
    if (!candidate.startsWith('{')) {
      continue;
    }
    try {
      const parsed = JSON.parse(candidate) as unknown;
      const error = validateRunnerEvidence(parsed);
      if (error) {
        throw new Error(error);
      }
      return parsed as RunnerEvidenceRequest;
    } catch {
      continue;
    }
  }
  throw new Error('runner output did not contain valid JSON evidence');
}

export function validateRunnerEvidence(value: unknown): string | null {
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

export function buildRunnerErrorEvidence(
  candidateSha: string,
  type: string,
  message: string,
): RunnerEvidenceRequest {
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

async function writeFixture(fixture: FixtureBundle, runId: string): Promise<string> {
  const baseDir = process.env.RUNNER_TEMP || os.tmpdir();
  const filePath = path.join(baseDir, `zroky-fixture-${runId}.json`);
  await fs.writeFile(filePath, JSON.stringify(fixture, null, 2), 'utf8');
  return filePath;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
