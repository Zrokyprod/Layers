from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


EvidenceManifestFilter = Literal["all", "matched", "needs_verification", "exceptions"]
EvidenceManifestExportKind = Literal["receipt", "evidence_pack"] | None
EvidenceManifestKind = Literal["action_receipt", "orphan_decision", "unlinked_outcome"]


class EvidenceManifestScope(BaseModel):
    filter: EvidenceManifestFilter
    search: str | None
    start_date: str | None
    end_date: str | None
    total_records: int
    exportable_records: int
    non_exportable_records: int
    window_days: int | None = None


class EvidenceManifestVerification(BaseModel):
    public_key_url: str
    instructions: list[str]


class EvidenceManifestRecord(BaseModel):
    action_id: str | None
    checked_at: datetime | None
    decision_id: str | None
    digest: str | None
    export_kind: EvidenceManifestExportKind
    exportable: bool
    href: str
    id: str
    kind: EvidenceManifestKind
    source_label: str
    status: str
    system_ref: str | None
    title: str
    trace_id: str | None


class EvidenceManifestResponse(BaseModel):
    artifact: Literal["zroky.evidence_manifest"]
    schema_version: Literal["zroky.evidence_manifest.v1"]
    generated_at: datetime
    project_id: str
    scope: EvidenceManifestScope
    verification: EvidenceManifestVerification
    records: list[EvidenceManifestRecord]


class EvidenceLedgerCounts(BaseModel):
    exceptions: int
    export_ready: int
    needs_verification: int
    total: int


class EvidenceLedgerRecord(BaseModel):
    action_id: str | None
    action_type: str
    agent_name: str
    call_id: str | None
    checked_at: datetime | None
    decision_id: str | None
    detail: str
    digest: str | None
    export_kind: EvidenceManifestExportKind
    exportable: bool
    href: str
    id: str
    kind: EvidenceManifestKind
    outcome_id: str | None
    source_label: str
    status: str
    system_ref: str | None
    title: str
    trace_id: str | None


class EvidenceLedgerResponse(BaseModel):
    counts: EvidenceLedgerCounts
    has_more: bool
    items: list[EvidenceLedgerRecord]
    limit: int
    offset: int
    total_in_scope: int
    total_matching: int
    window_days: int
