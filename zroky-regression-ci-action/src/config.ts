import * as fs from 'fs/promises';

export interface ZrokyActionConfig {
  raw?: string;
  runner?: {
    command?: string;
    timeoutSeconds?: number;
  };
  replay?: {
    toolMode?: string;
    trials?: number;
  };
  contracts?: {
    include: string[];
  };
}

export async function loadZrokyConfig(configPath: string): Promise<ZrokyActionConfig> {
  try {
    const raw = await fs.readFile(configPath, 'utf8');
    return { ...parseZrokyYaml(raw), raw };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT') {
      return {};
    }
    throw error;
  }
}

export function parseZrokyYaml(raw: string): ZrokyActionConfig {
  const config: ZrokyActionConfig = { contracts: { include: [] } };
  let section = '';
  let nested = '';

  for (const originalLine of raw.split(/\r?\n/)) {
    const line = originalLine.replace(/\s+#.*$/, '');
    if (!line.trim() || line.trimStart().startsWith('#')) {
      continue;
    }
    const indent = line.match(/^\s*/)?.[0].length ?? 0;
    const trimmed = line.trim();

    if (indent === 0) {
      nested = '';
      if (trimmed.endsWith(':')) {
        section = trimmed.slice(0, -1).trim();
        continue;
      }
      const pair = splitPair(trimmed);
      if (pair) {
        section = pair.key;
      }
      continue;
    }

    if (section === 'runner') {
      const pair = splitPair(trimmed);
      if (!pair) {
        continue;
      }
      config.runner = config.runner || {};
      if (pair.key === 'command') {
        config.runner.command = parseScalar(pair.value);
      } else if (pair.key === 'timeout_seconds') {
        config.runner.timeoutSeconds = parseInteger(pair.value);
      }
      continue;
    }

    if (section === 'replay') {
      const pair = splitPair(trimmed);
      if (!pair) {
        continue;
      }
      config.replay = config.replay || {};
      if (pair.key === 'tool_mode') {
        config.replay.toolMode = parseScalar(pair.value);
      } else if (pair.key === 'trials') {
        config.replay.trials = parseInteger(pair.value);
      }
      continue;
    }

    if (section === 'contracts') {
      const pair = splitPair(trimmed);
      if (pair && pair.key === 'include') {
        nested = 'include';
        config.contracts = { include: parseList(pair.value) };
        continue;
      }
      if (nested === 'include' && trimmed.startsWith('-')) {
        const value = parseScalar(trimmed.slice(1).trim());
        if (value) {
          config.contracts = config.contracts || { include: [] };
          config.contracts.include.push(value);
        }
      }
    }
  }

  return config;
}

function splitPair(line: string): { key: string; value: string } | null {
  const idx = line.indexOf(':');
  if (idx < 0) {
    return null;
  }
  return {
    key: line.slice(0, idx).trim(),
    value: line.slice(idx + 1).trim(),
  };
}

function parseScalar(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseInteger(value: string): number | undefined {
  const parsed = Number.parseInt(parseScalar(value), 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseList(value: string): string[] {
  const scalar = parseScalar(value);
  if (!scalar) {
    return [];
  }
  if (scalar.startsWith('[') && scalar.endsWith(']')) {
    return scalar
      .slice(1, -1)
      .split(',')
      .map((item) => parseScalar(item.trim()))
      .filter(Boolean);
  }
  return [];
}
