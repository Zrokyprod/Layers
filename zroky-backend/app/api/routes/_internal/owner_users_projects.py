from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor

@router.get("/stats", response_model=OwnerStatsResponse)
def owner_stats(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerStatsResponse:
    cutoff = datetime.now(UTC) - timedelta(days=7)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0
    total_calls = db.scalar(select(func.count()).select_from(Call)) or 0
    calls_last_7d = db.scalar(
        select(func.count()).select_from(Call).where(Call.created_at >= cutoff)
    ) or 0
    total_cost_usd = float(db.scalar(select(func.sum(Call.cost_total))) or 0.0)
    cost_last_7d_usd = float(
        db.scalar(select(func.sum(Call.cost_total)).where(Call.created_at >= cutoff)) or 0.0
    )
    new_users_last_7d = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= cutoff)
    ) or 0
    # Active = member of a project that had at least one call in the last 7 days
    active_users_last_7d = db.scalar(
        select(func.count(func.distinct(ProjectMembership.user_id)))
        .where(
            ProjectMembership.project_id.in_(
                select(Call.project_id).where(Call.created_at >= cutoff).distinct()
            )
        )
        .where(ProjectMembership.is_active.is_(True))
    ) or 0

    return OwnerStatsResponse(
        total_users=total_users,
        total_projects=total_projects,
        total_calls=total_calls,
        calls_last_7d=calls_last_7d,
        total_cost_usd=total_cost_usd,
        cost_last_7d_usd=cost_last_7d_usd,
        new_users_last_7d=new_users_last_7d,
        active_users_last_7d=active_users_last_7d,
    )


@router.get("/users", response_model=OwnerUsersResponse)
def owner_users(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=128),
    is_active: bool | None = Query(default=None),
) -> OwnerUsersResponse:
    pcount_subq = (
        select(ProjectMembership.user_id, func.count().label("pcount"))
        .group_by(ProjectMembership.user_id)
        .subquery()
    )
    base_q = (
        select(User, func.coalesce(pcount_subq.c.pcount, 0).label("project_count"))
        .outerjoin(pcount_subq, pcount_subq.c.user_id == User.id)
    )
    count_q = select(func.count()).select_from(User)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(User.display_name.ilike(pattern), User.github_login.ilike(pattern))
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    if is_active is not None:
        base_q = base_q.where(User.is_active.is_(is_active))
        count_q = count_q.where(User.is_active.is_(is_active))

    total = db.scalar(count_q) or 0
    rows = db.execute(base_q.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    result = [
        OwnerUserItem(
            id=u.id, email=u.email, github_login=u.github_login,
            display_name=u.display_name, is_active=u.is_active,
            created_at=u.created_at, project_count=int(pc),
        )
        for u, pc in rows
    ]
    return OwnerUsersResponse(users=result, total=total)


@router.get("/users/{user_id}", response_model=OwnerUserItem)
def owner_user_detail(
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerUserItem:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    pcount = db.scalar(
        select(func.count()).select_from(ProjectMembership).where(ProjectMembership.user_id == u.id)
    ) or 0
    return OwnerUserItem(
        id=u.id, email=u.email, github_login=u.github_login, display_name=u.display_name,
        is_active=u.is_active, created_at=u.created_at, project_count=pcount,
    )


class UserStatusRequest(BaseModel):
    is_active: bool
    reason: str | None = None


@router.patch("/users/{user_id}/status")
@limiter.limit("10/minute")
def owner_update_user_status(
    request: Request,
    user_id: str,
    body: UserStatusRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = bool(u.is_active)
    u.is_active = body.is_active  # type: ignore[assignment]
    _owner_audit(
        db,
        action="owner.user.activate" if body.is_active else "owner.user.deactivate",
        actor=_resolve_actor(request),
        target_id=user_id,
        metadata={"reason": body.reason, "previous_is_active": previous},
    )
    db.commit()
    return {"ok": True, "user_id": user_id, "is_active": body.is_active}


@router.get("/projects", response_model=OwnerProjectsResponse)
def owner_projects(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=128),
    is_active: bool | None = Query(default=None),
) -> OwnerProjectsResponse:
    call_stats_subq = (
        select(
            Call.project_id,
            func.count().label("call_count"),
            func.coalesce(func.sum(Call.cost_total), 0).label("total_cost"),
        )
        .group_by(Call.project_id)
        .subquery()
    )
    member_count_subq = (
        select(ProjectMembership.project_id, func.count().label("member_count"))
        .group_by(ProjectMembership.project_id)
        .subquery()
    )
    base_q = (
        select(
            Project,
            func.coalesce(call_stats_subq.c.call_count, 0).label("call_count"),
            func.coalesce(call_stats_subq.c.total_cost, 0.0).label("total_cost"),
            func.coalesce(member_count_subq.c.member_count, 0).label("member_count"),
        )
        .outerjoin(call_stats_subq, call_stats_subq.c.project_id == Project.id)
        .outerjoin(member_count_subq, member_count_subq.c.project_id == Project.id)
    )
    count_q = select(func.count()).select_from(Project)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(Project.name.ilike(pattern), Project.owner_ref.ilike(pattern))
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    if is_active is not None:
        base_q = base_q.where(Project.is_active.is_(is_active))
        count_q = count_q.where(Project.is_active.is_(is_active))

    total = db.scalar(count_q) or 0
    rows = db.execute(base_q.order_by(Project.created_at.desc()).limit(limit).offset(offset)).all()
    result = [
        OwnerProjectItem(
            id=p.id, name=p.name, owner_ref=p.owner_ref, is_active=p.is_active,
            created_at=p.created_at, call_count=int(cc), total_cost_usd=float(tc), member_count=int(mc),
        )
        for p, cc, tc, mc in rows
    ]
    return OwnerProjectsResponse(projects=result, total=total)


class UserMembershipItem(BaseModel):
    project_id: str
    project_name: str
    role: str
    is_active: bool
    joined_at: datetime


class UserMembershipsResponse(BaseModel):
    memberships: list[UserMembershipItem]


@router.get("/users/{user_id}/memberships", response_model=UserMembershipsResponse)
def owner_user_memberships(
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> UserMembershipsResponse:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = db.execute(
        select(ProjectMembership, Project.name)
        .join(Project, Project.id == ProjectMembership.project_id)
        .where(ProjectMembership.user_id == user_id)
        .order_by(ProjectMembership.created_at.desc())
    ).all()
    items = [
        UserMembershipItem(
            project_id=mem.project_id,
            project_name=name,
            role=mem.role,
            is_active=mem.is_active,
            joined_at=mem.created_at,
        )
        for mem, name in rows
    ]
    return UserMembershipsResponse(memberships=items)


@router.get("/projects/{project_id}", response_model=OwnerProjectItem)
def owner_project_detail(
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> OwnerProjectItem:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    call_count = db.scalar(select(func.count()).select_from(Call).where(Call.project_id == p.id)) or 0
    total_cost = float(db.scalar(select(func.sum(Call.cost_total)).where(Call.project_id == p.id)) or 0.0)
    member_count = db.scalar(
        select(func.count()).select_from(ProjectMembership).where(ProjectMembership.project_id == p.id)
    ) or 0
    return OwnerProjectItem(
        id=p.id, name=p.name, owner_ref=p.owner_ref, is_active=p.is_active,
        created_at=p.created_at, call_count=call_count, total_cost_usd=total_cost,
        member_count=member_count,
    )


class ProjectStatusRequest(BaseModel):
    is_active: bool
    reason: str | None = None


@router.patch("/projects/{project_id}/status")
@limiter.limit("10/minute")
def owner_update_project_status(
    request: Request,
    project_id: str,
    body: ProjectStatusRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    previous = bool(p.is_active)
    p.is_active = body.is_active  # type: ignore[assignment]
    _owner_audit(
        db,
        action="owner.project.activate" if body.is_active else "owner.project.deactivate",
        actor=_resolve_actor(request),
        target_id=project_id,
        metadata={"reason": body.reason, "project_name": p.name, "previous_is_active": previous},
    )
    db.commit()
    return {"ok": True, "project_id": project_id, "is_active": body.is_active}


class ProjectMemberItem(BaseModel):
    membership_id: str
    user_id: str
    email: str | None
    github_login: str | None
    display_name: str | None
    role: str
    is_active: bool
    joined_at: datetime


class ProjectMembersResponse(BaseModel):
    members: list[ProjectMemberItem]


@router.get("/projects/{project_id}/members", response_model=ProjectMembersResponse)
def owner_project_members(
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> ProjectMembersResponse:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    rows = db.execute(
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project_id)
        .order_by(ProjectMembership.created_at.desc())
    ).all()
    items = [
        ProjectMemberItem(
            membership_id=mem.id,
            user_id=user.id,
            email=user.email,
            github_login=user.github_login,
            display_name=user.display_name,
            role=mem.role,
            is_active=mem.is_active,
            joined_at=mem.created_at,
        )
        for mem, user in rows
    ]
    return ProjectMembersResponse(members=items)


__all__ = [name for name in globals() if not name.startswith("__")]
