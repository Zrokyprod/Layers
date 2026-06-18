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
          runner_required: true,
          fixture_url: '/v1/regression-ci/runs/run-1/fixture',
          run_token: 'token',
          contract_version_ids: ['contract-version-1'],
        },
      });

      const res = await client.dispatchRun({
        git_sha: 'sha-1',
        changed_files: [{ path: 'a.md' }],
      });

      expect(res.run_id).toBe('run-1');
      expect(res.runner_required).toBe(true);
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

  describe('repository runner API', () => {
    it('downloads fixture with the run token', async () => {
      mockGetJson.mockResolvedValue({
        statusCode: 200,
        result: {
          schema_version: 'zroky_fixture_bundle_v1',
          run_id: 'run-1',
          project_id: 'proj-abc',
          contract_version_ids: ['cv-1'],
          contracts: [],
          fixtures: [],
        },
      });

      const res = await client.getFixture('/v1/regression-ci/runs/run-1/fixture', 'token-1');
      expect(res.run_id).toBe('run-1');
      expect(mockGetJson).toHaveBeenCalledWith(
        'https://api.test/v1/regression-ci/runs/run-1/fixture',
        { 'X-Zroky-Run-Token': 'token-1' },
      );
    });

    it('uploads evidence with the run token', async () => {
      mockPostJson.mockResolvedValue({
        statusCode: 200,
        result: {
          run_id: 'run-1',
          status: 'pass',
          verdict: 'pass',
          trial_count: 10,
          required_trials: 10,
          critical_violation_count: 0,
        },
      });

      const evidence = {
        candidate_sha: 'sha-1',
        agent_release: { agent_name: 'Refund' },
        trials: Array.from({ length: 10 }, () => ({ status: 'pass' })),
        trace: {},
        business_outcome: {},
        state_diff: {},
        errors: [],
      };
      const res = await client.uploadEvidence('run-1', 'token-1', evidence);
      expect(res.status).toBe('pass');
      expect(mockPostJson).toHaveBeenCalledWith(
        'https://api.test/v1/regression-ci/runs/run-1/evidence',
        evidence,
        { 'X-Zroky-Run-Token': 'token-1' },
      );
    });
  });
});
