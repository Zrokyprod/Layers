import { FixtureBundle, RunnerEvidenceRequest } from './api';
export interface ExecuteRunnerOptions {
    command: string;
    timeoutSeconds: number;
    fixture: FixtureBundle;
    runId: string;
    candidateSha: string;
    contractVersionIds: string[];
}
export declare function executeRepositoryRunner(options: ExecuteRunnerOptions): Promise<RunnerEvidenceRequest>;
export declare function parseRunnerEvidence(stdout: string): RunnerEvidenceRequest;
export declare function validateRunnerEvidence(value: unknown): string | null;
export declare function buildRunnerErrorEvidence(candidateSha: string, type: string, message: string): RunnerEvidenceRequest;
