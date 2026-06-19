"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.failClosedMessage = failClosedMessage;
function failClosedMessage(detail) {
    if (detail.status === 'pass') {
        return null;
    }
    if (detail.status === 'fail') {
        const rate = detail.report?.regression_rate ?? 'unknown';
        return `Regression CI detected regressions (rate=${rate}). See the PR comment or dashboard for details.`;
    }
    if (detail.status === 'not_verified') {
        return 'Regression CI could not prove safety with active Contracts. See the PR comment or dashboard for missing proof.';
    }
    if (detail.status === 'error') {
        return 'Regression CI run encountered an error. See dashboard for details.';
    }
    return `Regression CI did not produce a passing verdict (status=${detail.status}). Only pass satisfies the required check.`;
}
//# sourceMappingURL=fail-closed.js.map