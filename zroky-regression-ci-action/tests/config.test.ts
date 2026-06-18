import { parseZrokyYaml } from '../src/config';

describe('parseZrokyYaml', () => {
  it('extracts repository runner settings', () => {
    const config = parseZrokyYaml(`
version: 1

runner:
  command: "python -m tests.zroky_runner"
  timeout_seconds: 180

replay:
  tool_mode: recorded
  trials: 10

contracts:
  include:
    - 11111111-1111-4111-8111-111111111111
`);

    expect(config.runner?.command).toBe('python -m tests.zroky_runner');
    expect(config.runner?.timeoutSeconds).toBe(180);
    expect(config.replay?.toolMode).toBe('recorded');
    expect(config.replay?.trials).toBe(10);
    expect(config.contracts?.include).toEqual(['11111111-1111-4111-8111-111111111111']);
  });

  it('supports inline contract include arrays', () => {
    const config = parseZrokyYaml(`
contracts:
  include: [aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa, bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb]
`);

    expect(config.contracts?.include).toEqual([
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    ]);
  });
});
