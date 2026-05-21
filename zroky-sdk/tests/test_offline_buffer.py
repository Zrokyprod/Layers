# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Tests for the SDK offline buffer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zroky._internal.offline_buffer import OfflineBuffer


@pytest.fixture()
def buffer(tmp_path: Path) -> OfflineBuffer:
    return OfflineBuffer(path=tmp_path / "offline.ndjson", max_bytes=100_000)


def test_starts_empty(buffer: OfflineBuffer) -> None:
    assert buffer.is_empty()
    assert buffer.size_bytes() == 0


def test_append_single_event(buffer: OfflineBuffer) -> None:
    buffer.append([{"call_id": "abc", "status": "success"}])
    assert not buffer.is_empty()
    assert buffer.size_bytes() > 0


def test_drain_returns_inserted_events(buffer: OfflineBuffer) -> None:
    events = [{"call_id": str(i)} for i in range(5)]
    buffer.append(events)
    drained = buffer.drain()
    assert drained == events
    assert buffer.is_empty()


def test_drain_preserves_order(buffer: OfflineBuffer) -> None:
    buffer.append([{"i": 1}])
    buffer.append([{"i": 2}, {"i": 3}])
    buffer.append([{"i": 4}])
    drained = buffer.drain()
    assert [e["i"] for e in drained] == [1, 2, 3, 4]


def test_drain_empty_returns_empty_list(buffer: OfflineBuffer) -> None:
    assert buffer.drain() == []


def test_max_bytes_caps_growth(tmp_path: Path) -> None:
    buf = OfflineBuffer(path=tmp_path / "tiny.ndjson", max_bytes=200)
    big_event = {"data": "x" * 1000}
    buf.append([big_event])
    # Single huge event exceeds the cap → dropped before write.
    assert buf.is_empty() or buf.size_bytes() <= 200


def test_clear_removes_file(buffer: OfflineBuffer) -> None:
    buffer.append([{"x": 1}])
    assert not buffer.is_empty()
    buffer.clear()
    assert buffer.is_empty()


def test_corrupt_lines_are_skipped(tmp_path: Path) -> None:
    p = tmp_path / "buf.ndjson"
    p.write_text(
        '{"valid":1}\nNOT JSON\n{"valid":2}\n',
        encoding="utf-8",
    )
    buf = OfflineBuffer(path=p, max_bytes=100_000)
    drained = buf.drain()
    assert drained == [{"valid": 1}, {"valid": 2}]


def test_append_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "persist.ndjson"
    OfflineBuffer(path=path).append([{"i": 1}, {"i": 2}])
    drained = OfflineBuffer(path=path).drain()
    assert [e["i"] for e in drained] == [1, 2]
