from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.provisioning import has_provisioning_access
from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token
from app.db.session import get_db_session
from app.services.membership import VALID_PROJECT_ROLES, get_membership

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
        project_id: str,
        request: Request,
        db: Session = Depends(get_db_session),
    ) -> None:
        if has_provisioning_access(request):
            return

        token = extract_bearer_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token for project role authorization.",
            )

        claims = decode_jwt_claims(token)
        identity = build_identity_context(claims)
        membership = get_membership(db, project_id=project_id, subject=identity.subject)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity is not a member of the requested project.",
            )

        if ROLE_RANK[membership.role] < ROLE_RANK[normalized_min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Project role '{membership.role}' does not allow this action.",
            )

    return _dependency
