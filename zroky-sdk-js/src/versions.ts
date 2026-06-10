// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import type { ZrokyConfig } from "./types";

export function versionMetadata(config: ZrokyConfig, model?: string): Record<string, unknown> | undefined {
  const versions: Record<string, unknown> = {
    code_sha: config.codeSha,
    deployment_id: config.deploymentId,
    model_version: config.modelVersion ?? model,
    tool_schema_version: config.toolSchemaVersion,
    rag_version: config.ragVersion,
    prompt_version: config.promptVersion,
  };
  const clean = Object.fromEntries(
    Object.entries(versions).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
  return Object.keys(clean).length ? clean : undefined;
}
