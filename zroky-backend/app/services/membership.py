from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProjectMembership, User

VALID_PROJECT_ROLES = {"owner", "admin", "member", "viewer"}


def normalize_project_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in VALID_PROJECT_ROLES:
        raise ValueError(f"Invalid project role: {role}")
    return normalized


def get_user_by_subject(db: Session, subject: str) -> User | None:
    query = select(User).where(User.subject == subject)
    return db.execute(query).scalar_one_or_none()


def get_or_create_user(db: Session, subject: str, email: str | None = None) -> User:
    user = get_user_by_subject(db, subject)
    if user is None:
        user = User(subject=subject, email=email, is_active=True)
        db.add(user)
        db.flush()
        return user

    if email and user.email != email:
        user.email = email
        db.flush()
    return user


def get_membership(db: Session, project_id: str, subject: str) -> ProjectMembership | None:
    query = (
        select(ProjectMembership)
        .join(User, User.id == ProjectMembership.user_id)
        .where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.is_active.is_(True),
            User.subject == subject,
            User.is_active.is_(True),
        )
    )
    return db.execute(query).scalar_one_or_none()


def upsert_project_membership(
    db: Session,
    *,
    project_id: str,
    subject: str,
    role: str,
    email: str | None = None,
    is_active: bool = True,
) -> ProjectMembership:
    normalized_role = normalize_project_role(role)
    user = get_or_create_user(db, subject=subject, email=email)

    query = select(ProjectMembership).where(
        ProjectMembership.project_id == project_id,
        ProjectMembership.user_id == user.id,
    )
    membership = db.execute(query).scalar_one_or_none()
    if membership is None:
        membership = ProjectMembership(
            project_id=project_id,
            user_id=user.id,
            role=normalized_role,
            is_active=is_active,
        )
        db.add(membership)
        db.flush()
        return membership

    membership.role = normalized_role
    membership.is_active = is_active
    db.flush()
    return membership
