from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor

class OwnerSupportTicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None


class OwnerSupportReplyRequest(BaseModel):
    body: str
    is_internal: bool = False


def _support_ticket_item(t: SupportTicket) -> dict:
    return {
        "ticket_id": t.id,
        "tenant_id": t.tenant_id,
        "user_id": t.user_id,
        "subject": t.subject,
        "email": t.email,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "assigned_to": t.assigned_to,
        "resolved_at": t.resolved_at,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "message_count": len(t.messages),
    }


def _support_message_item(m: SupportTicketMessage) -> dict:
    return {
        "message_id": m.id,
        "sender_type": m.sender_type,
        "sender_subject": m.sender_subject,
        "body": m.body,
        "is_internal": m.is_internal,
        "created_at": m.created_at,
    }


@router.get("/support/tickets")
def owner_list_support_tickets(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    ticket_status: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    q = select(SupportTicket).order_by(SupportTicket.created_at.desc())
    count_q = select(func.count()).select_from(SupportTicket)
    if ticket_status:
        q = q.where(SupportTicket.status == ticket_status)
        count_q = count_q.where(SupportTicket.status == ticket_status)
    if priority:
        q = q.where(SupportTicket.priority == priority)
        count_q = count_q.where(SupportTicket.priority == priority)
    if tenant_id:
        q = q.where(SupportTicket.tenant_id == tenant_id)
        count_q = count_q.where(SupportTicket.tenant_id == tenant_id)
    if assigned_to:
        q = q.where(SupportTicket.assigned_to == assigned_to)
        count_q = count_q.where(SupportTicket.assigned_to == assigned_to)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return {
        "total": total,
        "items": [_support_ticket_item(t) for t in rows],
    }


@router.get("/support/tickets/{ticket_id}")
def owner_get_support_ticket(
    ticket_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return {
        "ticket": _support_ticket_item(ticket),
        "messages": [_support_message_item(m) for m in ticket.messages],
    }


@router.patch("/support/tickets/{ticket_id}")
@limiter.limit("20/minute")
def owner_update_support_ticket(
    request: Request,
    ticket_id: str,
    body: OwnerSupportTicketUpdateRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if body.status is not None:
        ticket.status = body.status
        if body.status == "resolved" and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(UTC)
    if body.priority is not None:
        ticket.priority = body.priority
    if body.assigned_to is not None:
        ticket.assigned_to = body.assigned_to
    _owner_audit(db, action="owner.support.ticket.update", actor=_resolve_actor(request),
                 target_id=ticket_id, metadata={"status": body.status, "assigned_to": body.assigned_to})
    db.commit()
    return {"ok": True, "ticket_id": ticket_id, "status": ticket.status}


@router.post("/support/tickets/{ticket_id}/reply", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def owner_reply_support_ticket(
    request: Request,
    ticket_id: str,
    body: OwnerSupportReplyRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    msg = SupportTicketMessage(
        ticket_id=ticket_id,
        sender_type="owner",
        sender_subject=_resolve_actor(request),
        body=body.body,
        is_internal=body.is_internal,
    )
    db.add(msg)
    ticket.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "message_id": msg.id, "ticket_id": ticket_id}


@router.get("/billing/summary")
def owner_billing_summary(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    plan_rows = db.execute(
        select(
            SubscriptionPlan.name,
            SubscriptionPlan.slug,
            func.count(TenantSubscription.id).label("tenant_count"),
        )
        .outerjoin(TenantSubscription, TenantSubscription.plan_id == SubscriptionPlan.id)
        .where(SubscriptionPlan.is_active.is_(True))
        .group_by(SubscriptionPlan.name, SubscriptionPlan.slug)
        .order_by(SubscriptionPlan.slug)
    ).all()

    status_rows = db.execute(
        select(TenantSubscription.status, func.count().label("count"))
        .group_by(TenantSubscription.status)
    ).all()

    total_subscriptions = db.scalar(select(func.count()).select_from(TenantSubscription)) or 0
    overdue = db.scalar(
        select(func.count()).select_from(TenantSubscription)
        .where(TenantSubscription.status == "past_due")
    ) or 0
    canceled = db.scalar(
        select(func.count()).select_from(TenantSubscription)
        .where(TenantSubscription.status == "canceled")
    ) or 0

    return {
        "total_subscriptions": total_subscriptions,
        "overdue": overdue,
        "canceled": canceled,
        "by_plan": [
            {"plan": name, "slug": slug, "tenant_count": int(count)}
            for name, slug, count in plan_rows
        ],
        "by_status": [
            {"status": s, "count": int(c)} for s, c in status_rows
        ],
    }


@router.get("/billing/accounts")
def owner_billing_accounts(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    account_status: str | None = Query(default=None, alias="status"),
    plan_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    q = (
        select(Subscription, Project.name)
        .outerjoin(Project, Project.id == Subscription.org_id)
        .order_by(Subscription.updated_at.desc())
    )
    count_q = select(func.count()).select_from(Subscription)
    if account_status:
        q = q.where(Subscription.status == account_status)
        count_q = count_q.where(Subscription.status == account_status)
    if plan_code:
        q = q.where(Subscription.plan_code == plan_code)
        count_q = count_q.where(Subscription.plan_code == plan_code)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).all()

    def stripe_customer_url(customer_id: str | None) -> str | None:
        return f"https://dashboard.stripe.com/customers/{customer_id}" if customer_id else None

    def stripe_subscription_url(subscription_id: str | None) -> str | None:
        return f"https://dashboard.stripe.com/subscriptions/{subscription_id}" if subscription_id else None

    return {
        "total": total,
        "items": [
            {
                "org_id": sub.org_id,
                "project_name": project_name,
                "plan_code": sub.plan_code,
                "status": sub.status,
                "sla_tier": sub.sla_tier,
                "seats": sub.seats,
                "current_period_end": sub.current_period_end,
                "trial_end": sub.trial_end,
                "stripe_customer_id": sub.stripe_customer_id,
                "stripe_sub_id": sub.stripe_sub_id,
                "stripe_customer_url": stripe_customer_url(sub.stripe_customer_id),
                "stripe_subscription_url": stripe_subscription_url(sub.stripe_sub_id),
                "updated_at": sub.updated_at,
            }
            for sub, project_name in rows
        ],
    }


__all__ = [name for name in globals() if not name.startswith("__")]
