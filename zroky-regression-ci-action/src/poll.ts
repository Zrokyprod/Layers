/**
 * Poll the GET endpoint until the run reaches a terminal state.
 */

import { ZrokyApiClient, RegressionCIRunDetailResponse } from './api';

const TERMINAL_STATUSES = new Set(['pass', 'warn', 'fail', 'not_verified', 'error']);

export interface PollOptions {
  intervalSeconds: number;
  timeoutSeconds: number;
}

export interface PollResult {
  detail: RegressionCIRunDetailResponse;
  elapsedMs: number;
  pollCount: number;
}

export async function pollUntilTerminal(
  client: ZrokyApiClient,
  runId: string,
  options: PollOptions,
): Promise<PollResult> {
  const deadline = Date.now() + options.timeoutSeconds * 1000;
  const intervalMs = options.intervalSeconds * 1000;
  let pollCount = 0;

  while (true) {
    const detail = await client.getRun(runId);
    pollCount++;

    if (TERMINAL_STATUSES.has(detail.status)) {
      return {
        detail,
        elapsedMs: Date.now() - (deadline - options.timeoutSeconds * 1000),
        pollCount,
      };
    }

    if (Date.now() >= deadline) {
      throw new Error(
        `Timeout after ${options.timeoutSeconds}s (${pollCount} polls). ` +
          `Last status: ${detail.status}`,
      );
    }

    await sleep(intervalMs);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
