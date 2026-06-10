from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import has_strict_provisioning_access
from app.auth.identity import extract_bearer_token
from app.core.config import get_settings
from app.db.session import get_db_session
from app.services.membership import VALID_PROJECT_ROLES

ROLE_RANK: dict[str, int] = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}


def require_project_role(min_role: str) -> Callable:
    normalized_min_role = min_role.strip().lower()
    if normalized_min_role not in VALID_PROJECT_ROLES:
        raise ValueError(f"Unsupported role guard: {min_role}")

    def _dependency(
        request: Request,
        project_id: str | None = None,
        db: Session = Depends(get_db_session),
    ) -> str:
        if has_strict_provisioning_access(request):
            return project_id or ""

        settings = get_settings()
        has_api_key = bool((request.headers.get(settings.API_KEY_HEADER_NAME) or "").strip())
        has_bearer = bool(extract_bearer_token(request))
        if not has_api_key and not has_bearer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token or API key for project role authorization.",
            )

        from app.api.dependencies.tenant import (
            resolve_tenant_context_for_request,
            selected_project_id_from_request,
        )

        path_project_id = project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
        selected_project_id = selected_project_id_from_request(request)
        if selected_project_id and path_project_id and selected_project_id != path_project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Selected project does not match requested project.",
            )

        context = resolve_tenant_context_for_request(
            request,
            db,
            selected_project_id=selected_project_id or path_project_id,
            allow_header_context=False,
        )
        if path_project_id and context.tenant_id != path_project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Selected project does not match requested project.",
            )

        if ROLE_RANK[context.role] < ROLE_RANK[normalized_min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Project role '{context.role}' does not allow this action.",
            )

        return context.tenant_id

    return _dependency
