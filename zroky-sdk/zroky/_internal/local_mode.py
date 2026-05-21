# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
Local mode writer — persists call events to a local SQLite database
when ZROKY_MODE=local. No cloud account required.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from zroky._internal.pii import hash_identifier, mask_error_message

if TYPE_CHECKING:
    from zroky._internal.models import CallEvent

_DEFAULT_DB_PATH = Path.home() / ".zroky" / "local.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS call_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT    NOT NULL,
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    call_type   TEXT    NOT NULL DEFAULT 'chat',
    status      TEXT    NOT NULL,
    latency_ms  REAL,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    reasoning_tokens  INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    agent_name  TEXT,
    trace_id    TEXT,
    parent_call_id TEXT,
    user_id     TEXT,
    error_code  TEXT,
    error_message TEXT,
    payload_json TEXT,
    created_at  REAL    NOT NULL
);
"""

_INSERT_SQL = """
INSERT INTO call_events (
    call_id, provider, model, call_type, status,
    latency_ms, prompt_tokens, completion_tokens, reasoning_tokens,
    cache_creation_tokens, cache_read_tokens,
    agent_name, trace_id, parent_call_id, user_id,
    error_code, error_message, payload_json, created_at
) VALUES (
    :call_id, :provider, :model, :call_type, :status,
    :latency_ms, :prompt_tokens, :completion_tokens, :reasoning_tokens,
    :cache_creation_tokens, :cache_read_tokens,
    :agent_name, :trace_id, :parent_call_id, :user_id,
    :error_code, :error_message, :payload_json, :created_at
)
"""


class LocalWriter:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path or os.environ.get("ZROKY_LOCAL_DB", str(_DEFAULT_DB_PATH)))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def send_batch(self, events: list[CallEvent]) -> None:
        rows = [self._to_row(e) for e in events]
        with self._lock:
            self._conn.executemany(_INSERT_SQL, rows)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _to_row(event: CallEvent) -> dict:
        payload = event.to_ingest_payload()
        # Store full payload as JSON for portability
        return {
            "call_id": event.call_id,
            "provider": event.provider,
            "model": event.model,
            "call_type": event.call_type,
            "status": event.status,
            "latency_ms": event.latency_ms,
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "reasoning_tokens": event.reasoning_tokens,
            "cache_creation_tokens": event.cache_creation_tokens,
            "cache_read_tokens": event.cache_read_tokens,
            "agent_name": event.agent_name,
            "trace_id": event.trace_id,
            "parent_call_id": event.parent_call_id,
            "user_id": hash_identifier(event.user_id),
            "error_code": event.error_code,
            "error_message": (
                mask_error_message(event.error_message) if event.error_message else None
            ),
            "payload_json": json.dumps(payload, default=str),
            "created_at": event.created_at,
        }
