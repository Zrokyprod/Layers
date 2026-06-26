from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, AgentRelease, Environment


@dataclass(frozen=True)
class ReleaseIdentity:
    environment_id: str | None
    agent_id: str | None
    agent_release_id: str | None


_ENV_TYPES = {
    "prod": "production",
    "production": "production",
    "stage": "staging",
    "staging": "staging",
    "dev": "development",
    "development": "development",
    "test": "development",
    "testing": "development",
    "ci": "ci",
}


def resolve_release_identity(
    db: Session,
    *,
    project_id: str,
    payload: Mapping[str, Any],
    provider: str | None = None,
    model: str | None = None,
    agent_name: str | None = None,
    is_production: bool | None = None,
) -> ReleaseIdentity:
    """Create or reuse environment, agent, and release rows from capture metadata.

    A release is only created when deploy/version evidence exists. Provider and
    model alone are useful for filtering but too weak to prove a candidate
    release, so low-metadata legacy rows receive only environment/agent links.
    """
    env_name = _environment_name(payload, is_production=is_production)
    environment = _get_or_create_environment(db, project_id=project_id, name=env_name)

    agent_label = _bounded_text(agent_name or payload.get("agent_name"), 255) or "unknown-agent"
    agent = _get_or_create_agent(db, project_id=project_id, name=agent_label)

    versions = _versions(payload)
    release_fields = _release_fields(
        payload=payload,
        versions=versions,
        provider=provider,
        model=model,
    )
    if not _has_strong_release_identity(release_fields):
        return ReleaseIdentity(environment.id, agent.id, None)

    fingerprint = _release_fingerprint(
        project_id=project_id,
        agent_slug=agent.slug,
        environment_name=environment.name,
        fields=release_fields,
    )
    release = db.execute(
        select(AgentRelease).where(
            AgentRelease.project_id == project_id,
            AgentRelease.agent_id == agent.id,
            AgentRelease.environment_id == environment.id,
            AgentRelease.release_fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
    if release is None:
        release = AgentRelease(
            id=str(uuid4()),
            project_id=project_id,
            agent_id=agent.id,
            environment_id=environment.id,
            release_fingerprint=fingerprint,
            metadata_json=json.dumps({"versions": versions}, separators=(",", ":"), sort_keys=True),
            **release_fields,
        )
        db.add(release)
        db.flush()
    return ReleaseIdentity(environment.id, agent.id, release.id)


def _environment_name(payload: Mapping[str, Any], *, is_production: bool | None) -> str:
    raw = _bounded_text(payload.get("environment"), 64)
    if raw:
        return raw.strip().lower()
    if is_production is False or payload.get("is_synthetic"):
        return "development"
    return "production"


def _environment_type(name: str) -> str:
    return _ENV_TYPES.get(name.strip().lower(), "custom")


def _get_or_create_environment(db: Session, *, project_id: str, name: str) -> Environment:
    existing = db.execute(
        select(Environment).where(Environment.project_id == project_id, Environment.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Environment(
        id=str(uuid4()),
        project_id=project_id,
        name=name,
        type=_environment_type(name),
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_agent(db: Session, *, project_id: str, name: str) -> Agent:
    slug = _slug(name)
    existing = db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Agent(id=str(uuid4()), project_id=project_id, name=name, slug=slug, runtime_path="sdk")
    db.add(row)
    db.flush()
    return row


def _versions(payload: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for source in (payload.get("versions"), payload.get("metadata")):
        if isinstance(source, Mapping):
            nested = source.get("versions")
            if isinstance(nested, Mapping):
                out.update({str(k): v for k, v in nested.items()})
            out.update({str(k): v for k, v in source.items() if k != "versions"})
    return out


def _release_fields(
    *,
    payload: Mapping[str, Any],
    versions: Mapping[str, Any],
    provider: str | None,
    model: str | None,
) -> dict[str, Any]:
    return {
        "git_sha": _first_text(
            (versions, payload),
            "code_sha",
            "git_sha",
            "commit_sha",
            "sha",
        ),
        "application_version": _first_text(
            (versions, payload),
            "application_version",
            "app_version",
            "deployment_id",
            "release",
        ),
        "prompt_version": _first_text((versions, payload), "prompt_version", "prompt_id"),
        "model_provider": _bounded_text(provider or payload.get("provider"), 120),
        "model_name": _first_text((versions, payload), "model_version", "model_name", "model") or _bounded_text(model, 120),
        "model_parameters_hash": _first_text((versions, payload), "model_parameters_hash", "model_config_hash"),
        "tool_schema_hash": _first_text(
            (versions, payload),
            "tool_schema_hash",
            "tool_schema_version",
            "tool_schema_ver",
        ),
        "retrieval_version": _first_text(
            (versions, payload),
            "retrieval_version",
            "rag_version",
            "retriever_version",
        ),
    }


def _has_strong_release_identity(fields: Mapping[str, Any]) -> bool:
    return any(
        fields.get(key)
        for key in (
            "git_sha",
            "application_version",
            "prompt_version",
            "model_parameters_hash",
            "tool_schema_hash",
            "retrieval_version",
        )
    )


def _release_fingerprint(
    *,
    project_id: str,
    agent_slug: str,
    environment_name: str,
    fields: Mapping[str, Any],
) -> str:
    payload = {
        "project_id": project_id,
        "agent_slug": agent_slug,
        "environment": environment_name,
        **{key: fields.get(key) for key in sorted(fields)},
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_text(sources: tuple[Mapping[str, Any], ...], *keys: str) -> str | None:
    for key in keys:
        for source in sources:
            value = source.get(key)
            text = _bounded_text(value, 128)
            if text:
                return text
    return None


def _bounded_text(value: object, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:255] or "unknown-agent"
