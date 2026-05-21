import { ZrokyApiClient } from '../src/api';

// Mock the http-client
jest.mock('@actions/http-client', () => {
  return {
    HttpClient: jest.fn().mockImplementation(() => ({
      postJson: jest.fn(),
      getJson: jest.fn(),
    })),
    HttpClientResponse: jest.fn(),
  };
});

describe('ZrokyApiClient', () => {
  let client: ZrokyApiClient;
  let mockPostJson: jest.Mock;
  let mockGetJson: jest.Mock;

  beforeEach(() => {
    client = new ZrokyApiClient('https://api.test', 'key-123', 'proj-abc');
    const httpClient = (client as any).client;
    mockPostJson = httpClient.postJson;
    mockGetJson = httpClient.getJson;
  });

  describe('dispatchRun', () => {
    it('returns the run on 202', async () => {
      mockPostJson.mockResolvedValue({
        statusCode: 202,
        result: {
          run_id: 'run-1',
          project_id: 'proj-abc',
          git_sha: 'sha-1',
          status: 'pending',
          summary_url: '/v1/regression-ci/runs/run-1',
        },
      });

      const res = await client.dispatchRun({
        git_sha: 'sha-1',
        changed_files: [{ path: 'a.md' }],
      });

      expect(res.run_id).toBe('run-1');
      expect(mockPostJson).toHaveBeenCalledWith(
        'https://api.test/v1/regression-ci/run',
        expect.objectContaining({ git_sha: 'sha-1' }),
      );
    });

    it('throws on non-202', async () => {
      mockPostJson.mockResolvedValue({ statusCode: 429, result: null });
      await expect(
        client.dispatchRun({ git_sha: 'sha-1', changed_files: [] }),
      ).rejects.toThrow('Dispatch failed: HTTP 429');
    });
  });

  describe('getRun', () => {
    it('returns detail on 200', async () => {
      mockGetJson.mockResolvedValue({
        statusCode: 200,
        result: { run_id: 'run-1', status: 'pass', project_id: 'proj-abc' },
      });

      const res = await client.getRun('run-1');
      expect(res.status).toBe('pass');
      expect(mockGetJson).toHaveBeenCalledWith(
        'https://api.test/v1/regression-ci/runs/run-1',
      );
    });

    it('throws on non-200', async () => {
      mockGetJson.mockResolvedValue({ statusCode: 404, result: null });
      await expect(client.getRun('run-1')).rejects.toThrow(
        'Poll failed: HTTP 404',
      );
    });
  });
});
