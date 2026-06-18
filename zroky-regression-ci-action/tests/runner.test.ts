import { buildRunnerErrorEvidence, parseRunnerEvidence, validateRunnerEvidence } from '../src/runner';

describe('runner evidence helpers', () => {
  it('parses valid JSON evidence from stdout', () => {
    const evidence = parseRunnerEvidence(`
log line
{"candidate_sha":"abc123","agent_release":{"agent_name":"Refund"},"trials":[{"status":"pass"}],"trace":{},"business_outcome":{},"state_diff":{},"errors":[]}
`);

    expect(evidence.candidate_sha).toBe('abc123');
    expect(evidence.trials).toHaveLength(1);
  });

  it('rejects missing required fields', () => {
    expect(validateRunnerEvidence({ candidate_sha: 'abc123' })).toBe('agent_release is required');
  });

  it('builds fail-closed runner error evidence', () => {
    const evidence = buildRunnerErrorEvidence('abc123', 'timeout', 'command timed out');
    expect(evidence.candidate_sha).toBe('abc123');
    expect(evidence.trials).toEqual([]);
    expect(evidence.errors[0]).toEqual(
      expect.objectContaining({ type: 'timeout', severity: 'error' }),
    );
  });
});
