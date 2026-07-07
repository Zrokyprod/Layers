from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Project, ProjectMembership, User

VALID_PROJECT_ROLES = {"owner", "admin", "member", "viewer"}


class LastProjectOwnerError(ValueError):
    """Raised when an update would leave a project without an active owner."""


class LastUserProjectOwnerError(ValueError):
    """Raised when account removal would orphan one or more projects."""


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


def projects_where_user_is_last_active_owner(db: Session, *, user_id: str) -> list[Project]:
    owned_projects = (
        db.execute(
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                ProjectMembership.user_id == user_id,
                ProjectMembership.role == "owner",
                ProjectMembership.is_active.is_(True),
                Project.is_active.is_(True),
            )
            .order_by(Project.name.asc(), Project.id.asc())
        )
        .scalars()
        .all()
    )

    blockers: list[Project] = []
    for project in owned_projects:
        active_owner_count = db.execute(
            select(func.count())
            .select_from(ProjectMembership)
            .where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.role == "owner",
                ProjectMembership.is_active.is_(True),
            )
        ).scalar_one()
        if active_owner_count <= 1:
            blockers.append(project)
    return blockers


def assert_user_can_delete_account(db: Session, *, user_id: str) -> None:
    blockers = projects_where_user_is_last_active_owner(db, user_id=user_id)
    if not blockers:
        return

    names = ", ".join(project.name for project in blockers[:3])
    suffix = "" if len(blockers) <= 3 else f", and {len(blockers) - 3} more"
    raise LastUserProjectOwnerError(
        "Transfer ownership before deleting this account. "
        f"You are the last active owner of {len(blockers)} project(s): {names}{suffix}."
    )


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

    if (
        membership.role == "owner"
        and membership.is_active
        and not (normalized_role == "owner" and is_active)
    ):
        active_owner_count = db.execute(
            select(func.count())
            .select_from(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.role == "owner",
                ProjectMembership.is_active.is_(True),
            )
        ).scalar_one()
        if active_owner_count <= 1:
            raise LastProjectOwnerError("Project must keep at least one active owner")

    membership.role = normalized_role
    membership.is_active = is_active
    db.flush()
    return membership
