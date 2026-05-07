from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DiagnosisSubmitRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    diagnosis_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]


class DiagnosisSubmitResponse(BaseModel):
    status: str
    diagnosis_id: str
    task_id: str | None = None


class DiagnosisStatusResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    status: str
    result_json: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DiagnosisFeedbackSubmitRequest(BaseModel):
    was_helpful: bool
    developer_note: str | None = Field(default=None, max_length=4000)

    @field_validator("developer_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DiagnosisFeedbackResponse(BaseModel):
    feedback_id: str
    tenant_id: str
    diagnosis_id: str
    was_helpful: bool
    developer_note: str | None
    created_by_subject: str | None
    created_at: datetime


class DiagnosisShareCreateResponse(BaseModel):
    share_id: str
    diagnosis_id: str
    token: str
    token_prefix: str
    expires_at: datetime
    created_at: datetime


class DiagnosisShareTokenResponse(BaseModel):
    share_id: str
    tenant_id: str
    diagnosis_id: str
    token_prefix: str
    created_by_subject: str | None
    expires_at: datetime
    revoked: bool
    created_at: datetime


class DiagnosisShareReadResponse(BaseModel):
    share_id: str
    diagnosis_id: str
    tenant_id: str
    status: str
    result_json: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    read_only: bool = True


class DiagnosisResolveResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    status: str
    resolved_at: datetime
    watch_expires_at: datetime
    target_categories: list[str]
    message: str


class DiagnosisFixWatchResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    status: str
    resolved_at: datetime | None
    watch_expires_at: datetime | None
    target_categories: list[str]
    recurrence_count: int
    last_recurrence_at: datetime | None
    message: str


class DiagnosisFixCopiedResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    action: str
    created_at: datetime


class DiagnosisGeneratePrRequest(BaseModel):
    fix_id: str | None = Field(default=None, min_length=1, max_length=128)
    repository_owner: str | None = Field(default=None, min_length=1, max_length=255)
    repository_name: str | None = Field(default=None, min_length=1, max_length=255)
    base_branch: str | None = Field(default=None, min_length=1, max_length=255)
    branch_name: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=12000)
    commit_message: str | None = Field(default=None, min_length=1, max_length=255)
    file_path: str | None = Field(default=None, min_length=1, max_length=1024)
    generated_patch: str | None = Field(default=None, min_length=1, max_length=120000)

    @field_validator(
        "fix_id",
        "repository_owner",
        "repository_name",
        "base_branch",
        "branch_name",
        "title",
        "commit_message",
        "file_path",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("body", "generated_patch", mode="before")
    @classmethod
    def normalize_multiline_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DiagnosisGeneratePrResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    fix_id: str
    auth_source: str
    repository_owner: str
    repository_name: str
    base_branch: str
    branch_name: str
    pull_request_number: int
    pull_request_url: str
    pull_request_title: str
    file_path: str
    commit_sha: str | None
    merge_commit_sha: str | None = None
    merged_at: datetime | None = None
    last_ci_state: str | None = None
    last_ci_conclusion: str | None = None
    last_ci_completed_at: datetime | None = None
    generated_patch: str
    created_at: datetime


class DiagnosisPrLinkResponse(BaseModel):
    pr_link_id: str
    tenant_id: str
    diagnosis_id: str
    fix_id: str | None = None
    repository_owner: str
    repository_name: str
    base_branch: str
    branch_name: str
    pull_request_number: int
    pull_request_url: str
    pull_request_title: str
    file_path: str
    commit_sha: str | None
    merge_commit_sha: str | None = None
    merged_at: datetime | None = None
    last_ci_state: str | None = None
    last_ci_conclusion: str | None = None
    last_ci_completed_at: datetime | None = None
    created_at: datetime


class DiagnosisUiStateResponse(BaseModel):
    tenant_id: str
    diagnosis_id: str
    assigned_subject: str | None = None
    snoozed_until: datetime | None = None
    dismissed: bool = False
    updated_at: datetime


class DiagnosisAssignmentRequest(BaseModel):
    assigned_subject: str | None = None


class DiagnosisSnoozeRequest(BaseModel):
    snoozed_until: datetime | None = None


class DiagnosisDismissRequest(BaseModel):
    dismissed: bool
