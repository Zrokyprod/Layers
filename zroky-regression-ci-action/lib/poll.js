"use strict";
/**
 * Poll the GET endpoint until the run reaches a terminal state.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.pollUntilTerminal = pollUntilTerminal;
const TERMINAL_STATUSES = new Set(['pass', 'fail', 'error']);
async function pollUntilTerminal(client, runId, options) {
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
            throw new Error(`Timeout after ${options.timeoutSeconds}s (${pollCount} polls). ` +
                `Last status: ${detail.status}`);
        }
        await sleep(intervalMs);
    }
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
//# sourceMappingURL=poll.js.map