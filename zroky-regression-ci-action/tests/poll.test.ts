import { ZrokyApiClient } from '../src/api';
import { pollUntilTerminal } from '../src/poll';

jest.mock('@actions/http-client');

describe('pollUntilTerminal', () => {
  let client: ZrokyApiClient;
  let mockGetJson: jest.Mock;

  beforeEach(() => {
    jest.useFakeTimers();
    client = new ZrokyApiClient('https://api.test', 'key', 'proj');
    mockGetJson = (client as any).client.getJson;
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns immediately on terminal status', async () => {
    mockGetJson.mockResolvedValue({
      statusCode: 200,
      result: { run_id: 'r1', status: 'pass', project_id: 'proj' },
    });

    const promise = pollUntilTerminal(client, 'r1', {
      intervalSeconds: 1,
      timeoutSeconds: 10,
    });

    const res = await promise;
    expect(res.detail.status).toBe('pass');
    expect(res.pollCount).toBe(1);
  });

  it('polls until terminal', async () => {
    mockGetJson
      .mockResolvedValueOnce({
        statusCode: 200,
        result: { run_id: 'r1', status: 'running', project_id: 'proj' },
      })
      .mockResolvedValueOnce({
        statusCode: 200,
        result: { run_id: 'r1', status: 'fail', project_id: 'proj' },
      });

    const promise = pollUntilTerminal(client, 'r1', {
      intervalSeconds: 1,
      timeoutSeconds: 10,
    });

    // Let the interval timer fire
    await jest.advanceTimersByTimeAsync(1500);
    const res = await promise;
    expect(res.detail.status).toBe('fail');
    expect(res.pollCount).toBe(2);
  });

  it('throws on timeout', async () => {
    mockGetJson.mockResolvedValue({
      statusCode: 200,
      result: { run_id: 'r1', status: 'running', project_id: 'proj' },
    });

    const promise = pollUntilTerminal(client, 'r1', {
      intervalSeconds: 1,
      timeoutSeconds: 2,
    });

    const assertion = expect(promise).rejects.toThrow('Timeout after 2s');
    await jest.advanceTimersByTimeAsync(3000);
    await assertion;
  });
});
