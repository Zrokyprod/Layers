"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadZrokyConfig = loadZrokyConfig;
exports.parseZrokyYaml = parseZrokyYaml;
const fs = __importStar(require("fs/promises"));
async function loadZrokyConfig(configPath) {
    try {
        const raw = await fs.readFile(configPath, 'utf8');
        return { ...parseZrokyYaml(raw), raw };
    }
    catch (error) {
        const code = error.code;
        if (code === 'ENOENT') {
            return {};
        }
        throw error;
    }
}
function parseZrokyYaml(raw) {
    const config = { contracts: { include: [] } };
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
            }
            else if (pair.key === 'timeout_seconds') {
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
            }
            else if (pair.key === 'trials') {
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
function splitPair(line) {
    const idx = line.indexOf(':');
    if (idx < 0) {
        return null;
    }
    return {
        key: line.slice(0, idx).trim(),
        value: line.slice(idx + 1).trim(),
    };
}
function parseScalar(value) {
    const trimmed = value.trim();
    if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
        (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
        return trimmed.slice(1, -1);
    }
    return trimmed;
}
function parseInteger(value) {
    const parsed = Number.parseInt(parseScalar(value), 10);
    return Number.isFinite(parsed) ? parsed : undefined;
}
function parseList(value) {
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
//# sourceMappingURL=config.js.map