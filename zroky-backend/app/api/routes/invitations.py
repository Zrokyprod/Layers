"""Project invitation routes.

Allows owners/admins to invite users by email, and invited users to accept
invitations via a secure token link.
"""
import secrets
from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.tenant import require_tenant_context, TenantContext
from app.core.limiter import limiter
from app.core.config import get_settings
from app.db.models import (
    Project,
    ProjectInvitation,
    ProjectMembership,
    User,
    compute_email_hash,
)
from app.db.session import get_db_session
from app.schemas.invitation import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    ProjectInvitationCreateRequest,
    ProjectInvitationResponse,
)
from app.services.membership import normalize_project_role, upsert_project_membership
from app.services.email_sender import send_email
from app.services.security import hash_api_key

router = APIRouter(prefix="/v1/invitations")

_INVITATION_TOKEN_BYTES = 32
_INVITATION_EXPIRE_DAYS = 7


def _hash_token(token: str) -> str:
    return hash_api_key(token)


def _invitation_to_response(
    invitation: ProjectInvitation,
    *,
    email_sent: bool | None = None,
) -> ProjectInvitationResponse:
    return ProjectInvitationResponse(
        invitation_id=invitation.id,
        project_id=invitation.project_id,
        email=invitation.email,
        role=invitation.role,
        invited_by_subject=invitation.invited_by_subject,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        email_sent=email_sent,
    )


def _send_invitation_email(
    *,
    invitation: ProjectInvitation,
    project: Project,
    raw_token: str,
) -> bool:
    settings = get_settings()
    accept_url = (
        f"{settings.FRONTEND_URL.rstrip('/')}/invite/accept"
        f"?token={quote(raw_token, safe='')}"
    )
    project_name = escape(project.name)
    role = escape(invitation.role)
    return send_email(
        to=[invitation.email],
        subject=f"You're invited to join {project.name} on Zroky",
        html_body=(
            "<p>Hi,</p>"
            f"<p>You've been invited to join <strong>{project_name}</strong> "
            f"on Zroky as <strong>{role}</strong>.</p>"
            f'<p><a href="{accept_url}">Accept invitation</a></p>'
            f"<p>This invitation expires in {_INVITATION_EXPIRE_DAYS} days.</p>"
            "<p>If you were not expecting this invitation, you can ignore this email.</p>"
        ),
        plain_body=(
            f"You've been invited to join '{project.name}' on Zroky as {invitation.role}.\n\n"
            f"Accept invitation: {accept_url}\n\n"
            f"This invitation expires in {_INVITATION_EXPIRE_DAYS} days."
        ),
    )


@router.post(
    "/projects/{project_id}/invitations",
    response_model=ProjectInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def create_invitation(
    request: Request,
    project_id: str,
    body: ProjectInvitationCreateRequest = Body(...),
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> ProjectInvitationResponse:
    """Create a new project invitation (owner or admin)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    normalized_role = normalize_project_role(body.role)
    normalized_email = body.email.strip().lower()

    existing_member = db.execute(
        select(ProjectMembership.id)
        .join(User, User.id == ProjectMembership.user_id)
        .where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.is_active.is_(True),
            User.is_active.is_(True),
            User.email_hash == compute_email_hash(normalized_email),
        )
    ).scalar_one_or_none()
    if existing_member is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already an active project member.",
        )

    # Prevent duplicate pending invitations
    existing = db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.email == normalized_email,
            ProjectInvitation.accepted_at.is_(None),
            ProjectInvitation.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email.",
        )

    raw_token = secrets.token_urlsafe(_INVITATION_TOKEN_BYTES)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(days=_INVITATION_EXPIRE_DAYS)

    invitation = ProjectInvitation(
        project_id=project_id,
        email=normalized_email,
        role=normalized_role,
        invited_by_subject=context.subject or "unknown",
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    email_sent = _send_invitation_email(
        invitation=invitation,
        project=project,
        raw_token=raw_token,
    )
    return _invitation_to_response(invitation, email_sent=email_sent)


@router.get(
    "/projects/{project_id}/invitations",
    response_model=list[ProjectInvitationResponse],
    dependencies=[Depends(require_project_role("admin"))],
)
def list_invitations(
    project_id: str,
    db: Session = Depends(get_db_session),
) -> list[ProjectInvitationResponse]:
    """List invitations for a project (owner/admin)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    invitations = db.execute(
        select(ProjectInvitation)
        .where(ProjectInvitation.project_id == project_id)
        .order_by(ProjectInvitation.created_at.desc())
    ).scalars().all()

    return [_invitation_to_response(inv) for inv in invitations]


@router.delete(
    "/projects/{project_id}/invitations/{invitation_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def revoke_invitation(
    request: Request,
    project_id: str,
    invitation_id: str,
    db: Session = Depends(get_db_session),
) -> None:
    """Revoke a pending invitation."""
    invitation = db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
    ).scalar_one_or_none()

    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation already accepted")

    invitation.revoked_at = datetime.now(UTC)
    db.commit()


@router.post(
    "/projects/{project_id}/invitations/{invitation_id}/resend",
    response_model=ProjectInvitationResponse,
    dependencies=[Depends(require_project_role("admin"))],
)
@limiter.limit("10/minute")
def resend_invitation(
    request: Request,
    project_id: str,
    invitation_id: str,
    db: Session = Depends(get_db_session),
) -> ProjectInvitationResponse:
    """Issue a fresh token and resend a pending invitation email."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    invitation = db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
    ).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation already accepted")
    if invitation.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation has been revoked")

    raw_token = secrets.token_urlsafe(_INVITATION_TOKEN_BYTES)
    invitation.token_hash = _hash_token(raw_token)
    invitation.expires_at = datetime.now(UTC) + timedelta(days=_INVITATION_EXPIRE_DAYS)
    db.commit()
    db.refresh(invitation)

    email_sent = _send_invitation_email(
        invitation=invitation,
        project=project,
        raw_token=raw_token,
    )
    return _invitation_to_response(invitation, email_sent=email_sent)


@router.post(
    "/accept",
    response_model=AcceptInvitationResponse,
)
@limiter.limit("10/minute")
def accept_invitation(
    request: Request,
    body: AcceptInvitationRequest = Body(...),
    db: Session = Depends(get_db_session),
    context: TenantContext = Depends(require_tenant_context),
) -> AcceptInvitationResponse:
    """Accept an invitation using the raw token."""
    token_hash = _hash_token(body.token.strip())
    invitation = db.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.token_hash == token_hash,
            ProjectInvitation.accepted_at.is_(None),
            ProjectInvitation.revoked_at.is_(None),
        )
    ).scalar_one_or_none()

    if invitation is None:
        return AcceptInvitationResponse(success=False, message="Invalid or expired invitation token.")

    expires_at = invitation.expires_at if invitation.expires_at.tzinfo is not None else invitation.expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires_at:
        return AcceptInvitationResponse(success=False, message="Invitation has expired.")

    # Resolve accepting user from context
    if not context.subject:
        return AcceptInvitationResponse(success=False, message="User identity not found.")
    user = db.execute(
        select(User).where(User.subject == context.subject)
    ).scalar_one_or_none()
    if user is None:
        return AcceptInvitationResponse(success=False, message="User identity not found.")
    if not user.email or user.email.strip().lower() != invitation.email:
        return AcceptInvitationResponse(
            success=False,
            message="Sign in with the email address that received this invitation.",
        )

    # Create or update membership
    membership = upsert_project_membership(
        db,
        project_id=invitation.project_id,
        subject=user.subject,
        email=user.email,
        role=invitation.role,
        is_active=True,
    )
    db.commit()
    db.refresh(membership)

    invitation.accepted_at = datetime.now(UTC)
    db.commit()

    return AcceptInvitationResponse(
        success=True,
        message="Invitation accepted. You now have access to the project.",
        project_id=invitation.project_id,
        membership_id=membership.id,
    )
