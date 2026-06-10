# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Pydantic models for the replay worker protocol."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class ReplayJob(BaseModel):
    replay_id: str
    trace_id: str
    fix_pr_id: str
    candidate_fix_diff: str
    artifact_url: str
    artifact_signature: str
    created_at: datetime
    timeout_seconds: int = 300


class ReplayResult(BaseModel):
    replay_id: str
    trace_id: str
    fix_pr_id: str
    status: Literal["pass", "fail", "error"]
    diff_metric: float | None = None
    embedding_cosine: float | None = None
    judge_verdict: str | None = None
    error_message: str | None = None
    stdout_tail: str | None = None
    completed_at: datetime


class PollResponse(BaseModel):
    jobs: list[ReplayJob] = Field(default_factory=list)


class ResultPayload(BaseModel):
    worker_token: str
    worker_id: str | None = None
    result: ReplayResult
