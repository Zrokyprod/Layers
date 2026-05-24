// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import { _setOutcomeConfig } from "./outcome";
import type { ZrokyConfig } from "./types";

let defaultConfig: ZrokyConfig = {};

export function init(config: ZrokyConfig): void {
  defaultConfig = { ...config };
  _setOutcomeConfig(defaultConfig);
}

export function resolveConfig(config: ZrokyConfig = {}): ZrokyConfig {
  return { ...defaultConfig, ...config };
}
