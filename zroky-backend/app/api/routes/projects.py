from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.provisioning import require_provisioning_access
from app.core.limiter import limiter
from app.db.models import ApiKey, DiagnosisShareToken, Project, ProjectMembership, User, compute_email_hash
from app.db.session import get_db_session
from app.schemas.diagnosis import DiagnosisShareTokenResponse
from app.schemas.project import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ProjectMembershipResponse,
    ProjectMembershipUpsertRequest,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectInviteRequest,
    ProjectInviteResponse,
)
from app.services.email_sender import send_email
from app.services.membership import normalize_project_role, upsert_project_membership as upsert_project_membership_record
from app.services.security import generate_api_key_material, generate_project_id

router = APIRouter(prefix="/v1/projects")


def _project_to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.id,
        name=project.name,
        owner_ref=project.owner_ref,
        is_active=project.is_active,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _api_key_to_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        key_id=api_key.id,
        project_id=api_key.project_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        revoked=api_key.revoked_at is not None,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


def _membership_to_response(
    membership: ProjectMembership,
    user: User,
) -> ProjectMembershipResponse:
    return ProjectMembershipResponse(
        membership_id=membership.id,
        project_id=membership.project_id,
        user_id=membership.user_id,
        subject=user.subject,
        email=user.email,
        role=membership.role,
        is_active=membership.is_active,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _share_token_to_response(share_token: DiagnosisShareToken) -> DiagnosisShareTokenResponse:
    return DiagnosisShareTokenResponse(
        share_id=share_token.id,
        tenant_id=share_token.tenant_id,
        diagnosis_id=share_token.diagnosis_id,
        token_prefix=share_token.token_prefix,
        created_by_subject=share_token.created_by_subject,
        expires_at=share_token.expires_at,
        revoked=share_token.revoked_at is not None,
        created_at=share_token.created_at,
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_provisioning_access)],
)
@limiter.limit("10/minute")
def create_project(
    request: Request,
    body: ProjectCreateRequest,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    project = Project(
        id=generate_project_id(),
        name=body.name.strip(),
        owner_ref=body.owner_ref.strip() if body.owner_ref else None,
        is_active=True,
    )
    db.add(project)

    if body.owner_ref:
        upsert_project_membership_record(
            db,
            project_id=project.id,
            subject=body.owner_ref.strip(),
            role="owner",
        )

    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.get("", response_model=list[ProjectResponse], dependencies=[Depends(require_provisioning_access)])
def list_projects(
    owner_ref: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> list[ProjectResponse]:
    query = select(Project).order_by(Project.created_at.desc()).limit(limit)
    if owner_ref:
        query = query.where(Project.owner_ref == owner_ref)

    projects = db.execute(query).scalars().all()
    return [_project_to_response(project) for project in projects]


@router.post(
    "/{project_id}/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("5/minute")
def create_api_key(
    request: Request,
    project_id: str,
    body: ApiKeyCreateRequest,
    db: Session = Depends(get_db_session),
) -> ApiKeyCreateResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not project.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project is inactive")

    raw_api_key, key_prefix, key_hash = generate_api_key_material()
    api_key = ApiKey(
        project_id=project_id,
        name=body.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyCreateResponse(
        key_id=api_key.id,
        project_id=api_key.project_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        api_key=raw_api_key,
        created_at=api_key.created_at,
    )


@router.get(
    "/{project_id}/api-keys",
    response_model=list[ApiKeyResponse],
    dependencies=[Depends(require_project_role("admin"))],
)
def list_api_keys(
    project_id: str,
    db: Session = Depends(get_db_session),
) -> list[ApiKeyResponse]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    query = select(ApiKey).where(ApiKey.project_id == project_id).order_by(ApiKey.created_at.desc())
    keys = db.execute(query).scalars().all()
    return [_api_key_to_response(api_key) for api_key in keys]


@router.post(
    "/{project_id}/api-keys/{key_id}/revoke",
    response_model=ApiKeyResponse,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def revoke_api_key(
    request: Request,
    project_id: str,
    key_id: str,
    db: Session = Depends(get_db_session),
) -> ApiKeyResponse:
    query = select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project_id)
    api_key = db.execute(query).scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(api_key)

    return _api_key_to_response(api_key)


@router.post(
    "/{project_id}/memberships",
    response_model=ProjectMembershipResponse,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def upsert_project_membership(
    request: Request,
    project_id: str,
    body: ProjectMembershipUpsertRequest,
    db: Session = Depends(get_db_session),
) -> ProjectMembershipResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    membership = upsert_project_membership_record(
        db,
        project_id=project_id,
        subject=body.subject,
        email=body.email,
        role=body.role,
        is_active=body.is_active,
    )
    db.commit()
    db.refresh(membership)

    user = db.get(User, membership.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Membership user missing")
    return _membership_to_response(membership, user)


@router.get(
    "/{project_id}/memberships",
    response_model=list[ProjectMembershipResponse],
    dependencies=[Depends(require_project_role("admin"))],
)
def list_project_memberships(
    project_id: str,
    db: Session = Depends(get_db_session),
) -> list[ProjectMembershipResponse]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    query = (
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project_id)
        .order_by(ProjectMembership.created_at.desc())
    )
    rows = db.execute(query).all()
    return [_membership_to_response(membership, user) for membership, user in rows]


@router.get(
    "/{project_id}/diagnosis-shares",
    response_model=list[DiagnosisShareTokenResponse],
    dependencies=[Depends(require_project_role("admin"))],
)
def list_project_diagnosis_shares(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> list[DiagnosisShareTokenResponse]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    query = (
        select(DiagnosisShareToken)
        .where(DiagnosisShareToken.tenant_id == project_id)
        .order_by(DiagnosisShareToken.created_at.desc())
        .limit(limit)
    )
    share_tokens = db.execute(query).scalars().all()
    return [_share_token_to_response(share_token) for share_token in share_tokens]


@router.post(
    "/{project_id}/diagnosis-shares/{share_id}/revoke",
    response_model=DiagnosisShareTokenResponse,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def revoke_project_diagnosis_share(
    request: Request,
    project_id: str,
    share_id: str,
    db: Session = Depends(get_db_session),
) -> DiagnosisShareTokenResponse:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    query = select(DiagnosisShareToken).where(
        DiagnosisShareToken.id == share_id,
        DiagnosisShareToken.tenant_id == project_id,
    )
    share_token = db.execute(query).scalar_one_or_none()
    if share_token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis share token not found")

    if share_token.revoked_at is None:
        share_token.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(share_token)

    return _share_token_to_response(share_token)


@router.post(
    "/{project_id}/invite",
    response_model=ProjectInviteResponse,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("20/minute")
def invite_project_member(
    request: Request,
    project_id: str,
    body: ProjectInviteRequest,
    db: Session = Depends(get_db_session),
) -> ProjectInviteResponse:
    """Invite a user to a project by email. If they already exist, add them directly."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    existing_user = db.execute(
        select(User).where(User.email_hash == compute_email_hash(body.email.strip().lower()))
    ).scalar_one_or_none()

    if existing_user is not None:
        upsert_project_membership_record(
            db=db,
            project_id=project_id,
            subject=existing_user.subject,
            role=normalize_project_role(body.role),
        )
        send_email(
            to=[body.email],
            subject=f"You have been added to {project.name}",
            html_body=(
                f"<p>Hi,</p><p>You have been added to the project <strong>{project.name}</strong> on Zroky AI as a member.</p>"
                "<p>Log in to your account to get started.</p><p>The Zroky AI team</p>"
            ),
            plain_body=(
                f"Hi,\n\nYou have been added to the project '{project.name}' on Zroky AI as a member.\n\n"
                "Log in to your account to get started.\n\nThe Zroky AI team"
            ),
        )
        return ProjectInviteResponse(
            invited=True,
            message="User added to project and notified by email.",
            email=body.email,
        )

    # User doesn't exist — send an invitation email with a signup link
    from app.core.config import get_settings  # local import to avoid circular
    settings = get_settings()
    signup_url = f"{settings.FRONTEND_URL}/auth/register?invited_to={project_id}"
    send_email(
        to=[body.email],
        subject=f"You're invited to join {project.name} on Zroky AI",
        html_body=(
            f"<p>Hi,</p><p>You've been invited to join the project <strong>{project.name}</strong> on Zroky AI.</p>"
            f'<p><a href="{signup_url}">Create your account</a></p><p>The Zroky AI team</p>'
        ),
        plain_body=(
            f"Hi,\n\nYou've been invited to join the project '{project.name}' on Zroky AI.\n\n"
            f"Create your account here: {signup_url}\n\nThe Zroky AI team"
        ),
    )
    return ProjectInviteResponse(
        invited=True,
        message="Invitation email sent. The user will be added when they sign up.",
        email=body.email,
    )
