import { failClosedMessage } from '../src/fail-closed';

describe('failClosedMessage', () => {
  it('allows only pass by default', () => {
    expect(failClosedMessage({ status: 'pass' })).toBeNull();

    for (const status of ['fail', 'error', 'not_verified', 'warn', 'stale_sha', 'invalid_fixture']) {
      expect(
        failClosedMessage({ status, report: { regression_rate: 0.5 } }),
      ).toEqual(expect.any(String));
    }
  });

  it('explains non-pass terminal statuses', () => {
    expect(failClosedMessage({ status: 'fail', report: { regression_rate: 0.25 } })).toContain('rate=0.25');
    expect(failClosedMessage({ status: 'not_verified' })).toContain('could not prove safety');
    expect(failClosedMessage({ status: 'warn' })).toContain('Only pass satisfies');
  });
});
