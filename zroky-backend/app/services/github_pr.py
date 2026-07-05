from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx
from fastapi import HTTPException, status

from app.core.security_logging import sanitize_exception
from app.services.privacy import mask_text

_GITHUB_API_BASE = "https://api.github.com"
_BRANCH_SANITIZE_RE = re.compile(r"[^a-z0-9._/-]+")


@dataclass
class GeneratedPatch:
    file_path: str
    generated_patch: str
    title: str
    body: str
    commit_message: str
    branch_name: str


@dataclass
class GithubPullRequestResult:
    branch_name: str
    pull_request_number: int
    pull_request_url: str
    pull_request_title: str
    file_path: str
    commit_sha: str | None


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    if isinstance(parsed, dict):
        return parsed
    return {}


def _as_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    if value is None:
        return fallback

    try:
        rendered = str(value).strip()
    except Exception:
        return fallback
    return rendered or fallback


def _slug(value: str, *, fallback: str) -> str:
    normalized = _as_text(value).lower().replace(" ", "-")
    normalized = _BRANCH_SANITIZE_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-./")
    return normalized or fallback


def _safe_http_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return mask_text(response.text)[:500]

    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return mask_text(message.strip())
    return mask_text(str(payload))[:500]


def _first_diagnosis(result_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    diagnoses = result_payload.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        return {}

    first = diagnoses[0]
    if isinstance(first, Mapping):
        return first
    return {}


def build_generated_patch(
    *,
    diagnosis_id: str,
    diagnosis_payload_json: str | None,
    diagnosis_result_json: str | None,
    override_patch: str | None,
    override_file_path: str | None,
    override_title: str | None,
    override_body: str | None,
    override_commit_message: str | None,
    override_branch_name: str | None,
) -> GeneratedPatch:
    if override_patch:
        patch_content = mask_text(override_patch)
    else:
        result_payload = _safe_json_object(diagnosis_result_json)
        request_payload = _safe_json_object(diagnosis_payload_json)
        diagnosis = _first_diagnosis(result_payload)

        category = _as_text(diagnosis.get("category"), fallback="UNKNOWN")
        root_cause = mask_text(_as_text(diagnosis.get("root_cause"), fallback="No root cause available"))

        fix_mapping = diagnosis.get("fix") if isinstance(diagnosis, Mapping) else {}
        if not isinstance(fix_mapping, Mapping):
            fix_mapping = {}

        fix_primary = mask_text(_as_text(fix_mapping.get("primary"), fallback="Review diagnosis and apply safe remediation."))
        fix_code = mask_text(_as_text(fix_mapping.get("code"), fallback=""))
        fix_alternative = mask_text(_as_text(fix_mapping.get("alternative"), fallback=""))

        provider = _as_text(request_payload.get("provider"), fallback="unknown")
        model = _as_text(request_payload.get("model"), fallback="unknown")

        generated_at = datetime.now(timezone.utc).isoformat()
        patch_lines = [
            "# ZROKY Generated Fix Draft",
            "",
            f"- diagnosis_id: {diagnosis_id}",
            f"- generated_at: {generated_at}",
            f"- category: {category}",
            f"- provider: {provider}",
            f"- model: {model}",
            "",
            "## Root Cause",
            root_cause,
            "",
            "## Proposed Primary Fix",
            fix_primary,
            "",
        ]

        if fix_code:
            patch_lines.extend(
                [
                    "## Suggested Code Snippet",
                    "```python",
                    fix_code,
                    "```",
                    "",
                ]
            )

        if fix_alternative:
            patch_lines.extend(
                [
                    "## Alternative",
                    fix_alternative,
                    "",
                ]
            )

        patch_lines.extend(
            [
                "## Review Checklist",
                "- [ ] Confirm root cause against logs/traces",
                "- [ ] Apply fix in smallest safe change",
                "- [ ] Add/adjust tests to prevent regression",
                "- [ ] Roll out with monitoring",
                "",
            ]
        )

        patch_content = "\n".join(patch_lines).strip() + "\n"

    file_path = override_file_path or f"zroky-generated-fixes/{diagnosis_id}.md"
    title = override_title or f"[ZROKY Fix] {diagnosis_id}"
    body = mask_text(override_body) if override_body else (
        "Automated fix draft generated from diagnosis evidence.\n\n"
        "Please review and adapt before merging."
    )
    commit_message = override_commit_message or f"chore(zroky): add fix draft for {diagnosis_id}"
    branch_name = override_branch_name or f"zroky/fix/{_slug(diagnosis_id, fallback='diagnosis')}"

    return GeneratedPatch(
        file_path=file_path,
        generated_patch=patch_content,
        title=title,
        body=body,
        commit_message=commit_message,
        branch_name=branch_name,
    )


def create_pull_request_with_patch(  # noqa: F401  # noqa: replay-lint
    *,
    token: str,
    repository_owner: str,
    repository_name: str,
    base_branch: str,
    generated_patch: GeneratedPatch,
) -> GithubPullRequestResult:
    owner = _as_text(repository_owner)
    repo = _as_text(repository_name)
    base = _as_text(base_branch, fallback="main")
    branch = _as_text(generated_patch.branch_name)
    file_path = _as_text(generated_patch.file_path)

    if not token.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub token is not configured.",
        )

    if not owner or not repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository_owner and repository_name are required.",
        )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="branch_name is required.",
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(base_url=_GITHUB_API_BASE, headers=headers, timeout=15.0) as client:
        try:
            base_ref_response = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{base}")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            ) from sanitize_exception(exc)

        if base_ref_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Failed to resolve base branch '{base}' for {owner}/{repo}: "
                    f"{_safe_http_error_message(base_ref_response)}"
                ),
            )

        base_ref_payload = base_ref_response.json()
        base_sha = _as_text(base_ref_payload.get("object", {}).get("sha"))
        if not base_sha:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub base branch response missing commit SHA.",
            )

        create_ref_response = client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        if create_ref_response.status_code not in {201, 422}:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Failed to create branch '{branch}': "
                    f"{_safe_http_error_message(create_ref_response)}"
                ),
            )

        existing_file_sha: str | None = None
        file_response = client.get(f"/repos/{owner}/{repo}/contents/{file_path}", params={"ref": branch})
        if file_response.status_code == 200:
            file_payload = file_response.json()
            existing_file_sha = _as_text(file_payload.get("sha")) or None
        elif file_response.status_code != 404:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Failed to inspect file '{file_path}' on branch '{branch}': "
                    f"{_safe_http_error_message(file_response)}"
                ),
            )

        content_b64 = base64.b64encode(generated_patch.generated_patch.encode("utf-8")).decode("ascii")
        put_payload: dict[str, Any] = {
            "message": generated_patch.commit_message,
            "content": content_b64,
            "branch": branch,
        }
        if existing_file_sha:
            put_payload["sha"] = existing_file_sha

        upsert_file_response = client.put(
            f"/repos/{owner}/{repo}/contents/{file_path}",
            json=put_payload,
        )
        if upsert_file_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Failed to commit generated patch to '{file_path}': "
                    f"{_safe_http_error_message(upsert_file_response)}"
                ),
            )

        upsert_payload = upsert_file_response.json()
        commit_sha = _as_text(upsert_payload.get("commit", {}).get("sha")) or None

        create_pr_response = client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": generated_patch.title,
                "head": branch,
                "base": base,
                "body": generated_patch.body,
            },
        )

        if create_pr_response.status_code == 201:
            pr_payload = create_pr_response.json()
        elif create_pr_response.status_code == 422:
            existing_pr_response = client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={
                    "state": "open",
                    "head": f"{owner}:{branch}",
                    "base": base,
                    "per_page": 1,
                },
            )
            if existing_pr_response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "Failed to create PR and failed to query existing PR: "
                        f"{_safe_http_error_message(existing_pr_response)}"
                    ),
                )

            existing_payload = existing_pr_response.json()
            if not isinstance(existing_payload, list) or not existing_payload:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "GitHub rejected PR creation and no existing PR was found: "
                        f"{_safe_http_error_message(create_pr_response)}"
                    ),
                )
            pr_payload = existing_payload[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create pull request: {_safe_http_error_message(create_pr_response)}",
            )

    pr_number = int(pr_payload.get("number") or 0)
    pr_url = _as_text(pr_payload.get("html_url"))
    pr_title = _as_text(pr_payload.get("title"), fallback=generated_patch.title)

    if pr_number <= 0 or not pr_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub PR response missing required fields (number/html_url).",
        )

    return GithubPullRequestResult(
        branch_name=branch,
        pull_request_number=pr_number,
        pull_request_url=pr_url,
        pull_request_title=pr_title,
        file_path=file_path,
        commit_sha=commit_sha,
    )
