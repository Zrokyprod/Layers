/**
 * Poll the GET endpoint until the run reaches a terminal state.
 */
import { ZrokyApiClient, RegressionCIRunDetailResponse } from './api';
export interface PollOptions {
    intervalSeconds: number;
    timeoutSeconds: number;
}
export interface PollResult {
    detail: RegressionCIRunDetailResponse;
    elapsedMs: number;
    pollCount: number;
}
export declare function pollUntilTerminal(client: ZrokyApiClient, runId: string, options: PollOptions): Promise<PollResult>;
