"""Tenant-scoped connector credential custody and lifecycle management.

Connector configuration should describe *where* a credential is used, not
carry secret material itself. This module owns the small custody boundary:

* ``zroky_managed`` encrypts a value with the existing project-bound envelope.
* ``customer_managed`` and ``private_runner`` keep only an opaque secret ref.
* Credential versions are immutable. Rotation creates a new version and moves
  every connector binding atomically.

No serializer or audit payload in this module returns plaintext, ciphertext,
fingerprints, last-four values, or the full external secret reference.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ConnectorCredential,
    ConnectorCredentialAuditEvent,
    SystemOfRecordConnectorConfig,
)
from app.services.provider_key_cipher import (
    decrypt_provider_key,
    encrypt_provider_key,
)


CredentialKind = Literal["bearer_token", "oauth_refresh_token", "database_url"]
CustodyMode = Literal["zroky_managed", "customer_managed", "private_runner"]
CredentialPurpose = Literal["bearer_token", "oauth_refresh_token", "database_url"]

VALID_CREDENTIAL_KINDS = frozenset({"bearer_token", "oauth_refresh_token", "database_url"})
VALID_CUSTODY_MODES = frozenset({"zroky_managed", "customer_managed", "private_runner"})
VALID_SECRET_REF_SCHEMES = frozenset(
    {
        "runner",
        "vault",
        "aws-secretsmanager",
        "azure-keyvault",
        "gcp-secretmanager",
        "k8s",
        "custom",
    }
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
_CONNECTOR_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9:._*/-]{1,128}$")
_REF_RE = re.compile(r"^([a-z][a-z0-9-]{1,31})://[A-Za-z0-9][A-Za-z0-9._/-]{0,479}$")


class ConnectorCredentialError(ValueError):
    """Base error for caller-safe credential lifecycle failures."""


class CredentialNotFoundError(ConnectorCredentialError):
    """The requested credential does not belong to the tenant."""


class CredentialConflictError(ConnectorCredentialError):
    """The requested mutation conflicts with current credential state."""


class CredentialUnavailableError(ConnectorCredentialError):
    """A connector binding points at an inactive or expired credential."""


class RemoteCredentialResolutionRequired(ConnectorCredentialError):
    """A customer-managed/private-runner credential cannot run in-process."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_name(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _NAME_RE.fullmatch(normalized):
        raise ConnectorCredentialError(
            "credential name must use lowercase letters, numbers, dots, dashes, or underscores"
        )
    return normalized


def _normalize_kind(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in VALID_CREDENTIAL_KINDS:
        raise ConnectorCredentialError("unsupported credential kind")
    return normalized


def _normalize_custody_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in VALID_CUSTODY_MODES:
        raise ConnectorCredentialError("unsupported credential custody mode")
    return normalized


def _normalize_scopes(scopes: Iterable[str] | None) -> list[str]:
    values: list[str] = []
    for raw in scopes or []:
        scope = str(raw or "").strip()
        if not _SCOPE_RE.fullmatch(scope):
            raise ConnectorCredentialError("credential scopes contain an invalid value")
        if scope not in values:
            values.append(scope)
    if len(values) > 64:
        raise ConnectorCredentialError("a credential may contain at most 64 scopes")
    return values


def _normalize_allowed_connector_types(values: Iterable[str] | None) -> list[str]:
    connector_types: list[str] = []
    for raw in values or []:
        connector_type = str(raw or "").strip().lower()
        if not _CONNECTOR_TYPE_RE.fullmatch(connector_type):
            raise ConnectorCredentialError("allowed connector types contain an invalid value")
        if connector_type not in connector_types:
            connector_types.append(connector_type)
    if not connector_types:
        raise ConnectorCredentialError(
            "allowed connector types must explicitly scope every credential"
        )
    if len(connector_types) > 32:
        raise ConnectorCredentialError("a credential may target at most 32 connector types")
    return connector_types


def _normalize_secret_ref(value: str | None) -> str:
    normalized = str(value or "").strip()
    match = _REF_RE.fullmatch(normalized)
    if match is None or match.group(1) not in VALID_SECRET_REF_SCHEMES:
        raise ConnectorCredentialError(
            "secret_ref must use an approved reference scheme and must not contain secret material"
        )
    return normalized


def _validate_expiry(
    *,
    expires_at: datetime | None,
    rotation_due_at: datetime | None,
) -> None:
    if expires_at is not None and expires_at.tzinfo is None:
        raise ConnectorCredentialError("expires_at must include a timezone")
    if rotation_due_at is not None and rotation_due_at.tzinfo is None:
        raise ConnectorCredentialError("rotation_due_at must include a timezone")
    if expires_at and rotation_due_at and rotation_due_at > expires_at:
        raise ConnectorCredentialError("rotation_due_at cannot be after expires_at")


def _audit(
    db: Session,
    *,
    credential: ConnectorCredential,
    event_type: str,
    actor_subject: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    # Metadata is deliberately constructed by this service. Do not add caller
    # supplied data here: it could contain an accidentally pasted secret.
    db.add(
        ConnectorCredentialAuditEvent(
            id=str(uuid4()),
            project_id=credential.project_id,
            credential_id=credential.id,
            event_type=event_type,
            actor_subject=actor_subject,
            metadata_json=json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        )
    )


def _new_credential(
    *,
    project_id: str,
    name: str,
    version: int,
    credential_kind: str,
    custody_mode: str,
    plaintext_secret: str | None,
    secret_ref: str | None,
    scopes: list[str],
    allowed_connector_types: list[str],
    expires_at: datetime | None,
    rotation_due_at: datetime | None,
    created_by_subject: str | None,
    supersedes_id: str | None = None,
) -> ConnectorCredential:
    ciphertext: bytes | None = None
    fingerprint: str | None = None
    last4: str | None = None
    kms_key_id: str | None = None
    normalized_ref: str | None = None

    if custody_mode == "zroky_managed":
        secret = str(plaintext_secret or "").strip()
        if len(secret) < 8:
            raise ConnectorCredentialError("managed credential secret must be at least 8 characters")
        if secret_ref is not None:
            raise ConnectorCredentialError("managed credentials cannot include secret_ref")
        bundle = encrypt_provider_key(plaintext=secret, project_id=project_id)
        ciphertext = bundle.ciphertext
        fingerprint = bundle.key_fingerprint
        last4 = bundle.key_last4
        kms_key_id = bundle.kms_key_id
    else:
        if plaintext_secret is not None:
            raise ConnectorCredentialError(
                "customer-managed and private-runner credentials must not send secret plaintext"
            )
        normalized_ref = _normalize_secret_ref(secret_ref)

    return ConnectorCredential(
        id=str(uuid4()),
        project_id=project_id,
        name=name,
        version=version,
        credential_kind=credential_kind,
        custody_mode=custody_mode,
        secret_ref=normalized_ref,
        ciphertext=ciphertext,
        key_fingerprint=fingerprint,
        key_last4=last4,
        kms_key_id=kms_key_id,
        scopes_json=json.dumps(scopes, separators=(",", ":")),
        allowed_connector_types_json=json.dumps(
            allowed_connector_types, separators=(",", ":")
        ),
        expires_at=expires_at,
        rotation_due_at=rotation_due_at,
        supersedes_id=supersedes_id,
        is_active=True,
        created_by_subject=created_by_subject,
    )


def create_connector_credential(
    db: Session,
    *,
    project_id: str,
    name: str,
    credential_kind: str,
    custody_mode: str,
    plaintext_secret: str | None,
    secret_ref: str | None,
    scopes: Iterable[str] | None,
    allowed_connector_types: Iterable[str] | None,
    expires_at: datetime | None,
    rotation_due_at: datetime | None,
    actor_subject: str | None,
) -> ConnectorCredential:
    normalized_name = _normalize_name(name)
    if db.execute(
        select(ConnectorCredential.id).where(
            ConnectorCredential.project_id == project_id,
            ConnectorCredential.name == normalized_name,
        )
    ).first() is not None:
        raise CredentialConflictError("credential name already exists; rotate the existing credential")

    normalized_kind = _normalize_kind(credential_kind)
    normalized_custody = _normalize_custody_mode(custody_mode)
    normalized_scopes = _normalize_scopes(scopes)
    normalized_connector_types = _normalize_allowed_connector_types(allowed_connector_types)
    _validate_expiry(expires_at=expires_at, rotation_due_at=rotation_due_at)

    credential = _new_credential(
        project_id=project_id,
        name=normalized_name,
        version=1,
        credential_kind=normalized_kind,
        custody_mode=normalized_custody,
        plaintext_secret=plaintext_secret,
        secret_ref=secret_ref,
        scopes=normalized_scopes,
        allowed_connector_types=normalized_connector_types,
        expires_at=expires_at,
        rotation_due_at=rotation_due_at,
        created_by_subject=actor_subject,
    )
    db.add(credential)
    _audit(
        db,
        credential=credential,
        event_type="created",
        actor_subject=actor_subject,
        metadata={
            "credential_kind": credential.credential_kind,
            "custody_mode": credential.custody_mode,
            "version": credential.version,
        },
    )
    db.commit()
    db.refresh(credential)
    return credential


def get_connector_credential(
    db: Session, *, project_id: str, credential_id: str
) -> ConnectorCredential | None:
    return db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.project_id == project_id,
            ConnectorCredential.id == credential_id,
        )
    ).scalar_one_or_none()


def list_connector_credentials(
    db: Session, *, project_id: str, include_inactive: bool = False
) -> list[ConnectorCredential]:
    query = select(ConnectorCredential).where(ConnectorCredential.project_id == project_id)
    if not include_inactive:
        query = query.where(ConnectorCredential.is_active.is_(True))
    return list(
        db.execute(
            query.order_by(ConnectorCredential.name.asc(), ConnectorCredential.version.desc())
        ).scalars()
    )


def rotate_connector_credential(
    db: Session,
    *,
    project_id: str,
    credential_id: str,
    custody_mode: str,
    plaintext_secret: str | None,
    secret_ref: str | None,
    scopes: Iterable[str] | None,
    allowed_connector_types: Iterable[str] | None,
    expires_at: datetime | None,
    rotation_due_at: datetime | None,
    actor_subject: str | None,
) -> ConnectorCredential:
    previous = get_connector_credential(db, project_id=project_id, credential_id=credential_id)
    if previous is None:
        raise CredentialNotFoundError("credential was not found")
    if not previous.is_active:
        raise CredentialConflictError("only an active credential version can be rotated")

    normalized_custody = _normalize_custody_mode(custody_mode)
    normalized_scopes = _normalize_scopes(scopes)
    normalized_connector_types = _normalize_allowed_connector_types(allowed_connector_types)
    _validate_expiry(expires_at=expires_at, rotation_due_at=rotation_due_at)

    replacement = _new_credential(
        project_id=project_id,
        name=previous.name,
        version=previous.version + 1,
        credential_kind=previous.credential_kind,
        custody_mode=normalized_custody,
        plaintext_secret=plaintext_secret,
        secret_ref=secret_ref,
        scopes=normalized_scopes,
        allowed_connector_types=normalized_connector_types,
        expires_at=expires_at,
        rotation_due_at=rotation_due_at,
        created_by_subject=actor_subject,
        supersedes_id=previous.id,
    )
    now = _utc_now()
    previous.is_active = False
    previous.revoked_at = now
    db.add(previous)
    db.add(replacement)

    bindings = db.execute(
        select(SystemOfRecordConnectorConfig).where(
            SystemOfRecordConnectorConfig.project_id == project_id,
            (SystemOfRecordConnectorConfig.bearer_credential_id == previous.id)
            | (SystemOfRecordConnectorConfig.oauth_refresh_credential_id == previous.id)
            | (SystemOfRecordConnectorConfig.database_url_credential_id == previous.id),
        )
    ).scalars().all()
    for binding in bindings:
        if binding.bearer_credential_id == previous.id:
            binding.bearer_credential_id = replacement.id
        if binding.oauth_refresh_credential_id == previous.id:
            binding.oauth_refresh_credential_id = replacement.id
        if binding.database_url_credential_id == previous.id:
            binding.database_url_credential_id = replacement.id
        binding.updated_by_subject = actor_subject
        db.add(binding)

    _audit(
        db,
        credential=previous,
        event_type="rotated",
        actor_subject=actor_subject,
        metadata={"replacement_version": replacement.version, "binding_count": len(bindings)},
    )
    _audit(
        db,
        credential=replacement,
        event_type="rotated",
        actor_subject=actor_subject,
        metadata={"superseded_version": previous.version, "binding_count": len(bindings)},
    )
    db.commit()
    db.refresh(replacement)
    return replacement


def revoke_connector_credential(
    db: Session,
    *,
    project_id: str,
    credential_id: str,
    actor_subject: str | None,
) -> ConnectorCredential | None:
    credential = get_connector_credential(db, project_id=project_id, credential_id=credential_id)
    if credential is None:
        return None
    if credential.is_active:
        credential.is_active = False
        credential.revoked_at = _utc_now()
        db.add(credential)
        _audit(
            db,
            credential=credential,
            event_type="revoked",
            actor_subject=actor_subject,
            metadata={"version": credential.version},
        )
        db.commit()
        db.refresh(credential)
    return credential


_PURPOSE_FIELDS = {
    "bearer_token": "bearer_credential_id",
    "oauth_refresh_token": "oauth_refresh_credential_id",
    "database_url": "database_url_credential_id",
}
_LEGACY_FIELDS = {
    "bearer_token": (
        "bearer_token_ciphertext",
        "bearer_token_fingerprint",
        "bearer_token_last4",
    ),
    "oauth_refresh_token": (
        "oauth_refresh_token_ciphertext",
        "oauth_refresh_token_fingerprint",
        "oauth_refresh_token_last4",
    ),
    "database_url": (
        "database_url_ciphertext",
        "database_url_fingerprint",
        "database_url_last4",
    ),
}


def bind_connector_credential(
    db: Session,
    *,
    project_id: str,
    connector_type: str,
    credential_id: str,
    purpose: CredentialPurpose,
    actor_subject: str | None,
) -> SystemOfRecordConnectorConfig:
    normalized_type = str(connector_type or "").strip().lower()
    if not _CONNECTOR_TYPE_RE.fullmatch(normalized_type):
        raise ConnectorCredentialError("connector type is invalid")
    normalized_purpose = _normalize_kind(purpose)
    config = db.execute(
        select(SystemOfRecordConnectorConfig).where(
            SystemOfRecordConnectorConfig.project_id == project_id,
            SystemOfRecordConnectorConfig.connector_type == normalized_type,
        )
    ).scalar_one_or_none()
    if config is None:
        raise CredentialNotFoundError("connector configuration was not found")

    credential = get_connector_credential(db, project_id=project_id, credential_id=credential_id)
    if credential is None or not credential.is_active:
        raise CredentialNotFoundError("active credential was not found")
    if credential.credential_kind != normalized_purpose:
        raise ConnectorCredentialError("credential kind does not match the requested connector purpose")
    allowed_types = _json_list(credential.allowed_connector_types_json)
    if normalized_type not in allowed_types:
        raise ConnectorCredentialError("credential is not scoped to this connector type")

    setattr(config, _PURPOSE_FIELDS[normalized_purpose], credential.id)
    # Once a credential is deliberately bound, remove the legacy duplicate.
    # This also prevents a later remote-only binding from silently using the
    # previous Zroky-stored secret.
    for field in _LEGACY_FIELDS[normalized_purpose]:
        setattr(config, field, None)
    config.updated_by_subject = actor_subject
    db.add(config)
    _audit(
        db,
        credential=credential,
        event_type="bound",
        actor_subject=actor_subject,
        metadata={
            "connector_config_id": config.id,
            "connector_type": config.connector_type,
            "purpose": normalized_purpose,
            "legacy_secret_removed": True,
        },
    )
    db.commit()
    db.refresh(config)
    return config


def resolve_connector_credential(
    db: Session,
    *,
    row: SystemOfRecordConnectorConfig,
    project_id: str,
    purpose: CredentialPurpose,
) -> str | None:
    """Resolve a bound secret only for Zroky-managed custody.

    Bound remote-only credentials deliberately raise instead of falling back
    to an old in-row encrypted value. This prevents a custody change from
    accidentally keeping Zroky in possession of a credential.
    """
    if row.project_id != project_id:
        raise CredentialUnavailableError("connector project does not match credential request")
    normalized_purpose = _normalize_kind(purpose)
    credential_id = getattr(row, _PURPOSE_FIELDS[normalized_purpose])
    if not credential_id:
        return None
    credential = get_connector_credential(
        db, project_id=project_id, credential_id=credential_id
    )
    if credential is None or not credential.is_active:
        raise CredentialUnavailableError("connector credential is inactive or unavailable")
    if credential.credential_kind != normalized_purpose:
        raise CredentialUnavailableError("connector credential kind is invalid")
    now = _utc_now()
    if credential.expires_at is not None and credential.expires_at <= now:
        raise CredentialUnavailableError("connector credential has expired")
    if credential.custody_mode != "zroky_managed":
        raise RemoteCredentialResolutionRequired(
            "connector credential requires a private runner or customer-managed resolver"
        )
    if credential.ciphertext is None:
        raise CredentialUnavailableError("managed connector credential is unavailable")
    plaintext = decrypt_provider_key(ciphertext=credential.ciphertext, project_id=project_id)
    credential.last_used_at = now
    db.add(credential)
    db.flush()
    return plaintext


def list_connector_credential_audit_events(
    db: Session,
    *,
    project_id: str,
    credential_id: str,
) -> list[ConnectorCredentialAuditEvent]:
    if get_connector_credential(db, project_id=project_id, credential_id=credential_id) is None:
        raise CredentialNotFoundError("credential was not found")
    return list(
        db.execute(
            select(ConnectorCredentialAuditEvent)
            .where(
                ConnectorCredentialAuditEvent.project_id == project_id,
                ConnectorCredentialAuditEvent.credential_id == credential_id,
            )
            .order_by(
                ConnectorCredentialAuditEvent.created_at.desc(),
                ConnectorCredentialAuditEvent.id.desc(),
            )
        ).scalars()
    )


def _json_list(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _secret_ref_scheme(secret_ref: str | None) -> str | None:
    match = _REF_RE.fullmatch(secret_ref or "")
    return match.group(1) if match else None


def serialize_connector_credential(credential: ConnectorCredential) -> dict[str, Any]:
    now = _utc_now()
    state = "active"
    if not credential.is_active:
        state = "revoked"
    elif credential.expires_at is not None and credential.expires_at <= now:
        state = "expired"
    elif credential.custody_mode != "zroky_managed":
        state = "requires_private_runner"
    elif credential.rotation_due_at is not None and credential.rotation_due_at <= now:
        state = "rotation_due"
    return {
        "id": credential.id,
        "name": credential.name,
        "version": credential.version,
        "credential_kind": credential.credential_kind,
        "custody_mode": credential.custody_mode,
        "state": state,
        "reference_configured": credential.secret_ref is not None,
        "reference_scheme": _secret_ref_scheme(credential.secret_ref),
        "scopes": _json_list(credential.scopes_json),
        "allowed_connector_types": _json_list(credential.allowed_connector_types_json),
        "expires_at": credential.expires_at,
        "rotation_due_at": credential.rotation_due_at,
        "last_used_at": credential.last_used_at,
        "revoked_at": credential.revoked_at,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }


def serialize_connector_credential_audit_event(
    event: ConnectorCredentialAuditEvent,
) -> dict[str, Any]:
    try:
        metadata = json.loads(event.metadata_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    return {
        "id": event.id,
        "credential_id": event.credential_id,
        "event_type": event.event_type,
        "actor_subject": event.actor_subject,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": event.created_at,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
