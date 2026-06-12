from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor
from razorpay.errors import BadRequestError, GatewayError, ServerError

from app.api.routes.billing import (
    _razorpay_auth_failure,
    _razorpay_client,
    _razorpay_notes,
    _razorpay_order_is_paid,
    _razorpay_payment_is_captured,
)
from app.db.models import BillingEvent
from app.services.billing_plans import (
    InvalidPlanCodeError,
    normalize_plan_code,
)
from app.services.entitlements import clear_trial_entitlements, seed_plan_entitlements


class OwnerBillingPaymentConfirmRequest(BaseModel):
    org_id: str
    plan_code: str
    payment_ref: str
    customer_ref: str | None = None
    payment_request_ref: str | None = None
    current_period_end: datetime | None = None
    seats: int | None = None

class OwnerSupportTicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None


class OwnerSupportReplyRequest(BaseModel):
    body: str
    is_internal: bool = False


def _razorpay_entity_status(entity: dict) -> str:
    return str(entity.get("status") or "").strip().lower()


def _owner_razorpay_order_ref(value: str | None) -> str | None:
    if not value:
        return None
    order_ref, _, _plan_suffix = value.partition(":")
    return order_ref.strip() or None


def _fetch_razorpay_payment_for_owner(payment_ref: str) -> dict:
    try:
        payment = _razorpay_client().payment.fetch(payment_ref)
    except BadRequestError as exc:
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if _razorpay_auth_failure(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        detail = (
            "Razorpay authentication failed."
            if status_code == status.HTTP_401_UNAUTHORIZED
            else "Razorpay payment could not be verified."
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except (GatewayError, ServerError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay payment verification is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay payment verification failed.",
        ) from exc

    if not isinstance(payment, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay payment verification returned an invalid response.",
        )
    return payment


def _fetch_razorpay_order_for_owner(order_ref: str) -> dict:
    try:
        order = _razorpay_client().order.fetch(order_ref)
    except BadRequestError as exc:
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if _razorpay_auth_failure(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        detail = (
            "Razorpay authentication failed."
            if status_code == status.HTTP_401_UNAUTHORIZED
            else "Razorpay order could not be verified."
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except (GatewayError, ServerError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay order verification is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay order verification failed.",
        ) from exc

    if not isinstance(order, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay order verification returned an invalid response.",
        )
    return order


def _verify_owner_razorpay_payment(
    *,
    org_id: str,
    plan_code: str,
    payment_ref: str,
    requested_order_ref: str | None,
    stored_order_ref: str | None,
) -> tuple[dict, dict, str | None, bool]:
    payment = _fetch_razorpay_payment_for_owner(payment_ref)
    provider_payment_id = str(payment.get("id") or "").strip()
    if provider_payment_id and provider_payment_id != payment_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay payment response does not match payment_ref.",
        )

    payment_order_ref = str(payment.get("order_id") or "").strip() or None
    requested_order_ref = _owner_razorpay_order_ref(requested_order_ref)
    stored_order_ref = _owner_razorpay_order_ref(stored_order_ref)
    order_ref = requested_order_ref or stored_order_ref or payment_order_ref
    if requested_order_ref and payment_order_ref and requested_order_ref != payment_order_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payment_request_ref does not match the Razorpay payment order.",
        )

    order: dict = {}
    if order_ref:
        order = _fetch_razorpay_order_for_owner(order_ref)
        provider_order_id = str(order.get("id") or "").strip()
        if provider_order_id and provider_order_id != order_ref:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay order response does not match payment_request_ref.",
            )

    if not (_razorpay_payment_is_captured(payment) or _razorpay_order_is_paid(order)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Razorpay payment is not captured or order is not paid yet.",
        )

    notes = _razorpay_notes(payment, order)
    metadata_bound = False
    note_org_id = str(notes.get("org_id") or "").strip()
    if note_org_id:
        metadata_bound = True
        if note_org_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay metadata org_id does not match this org.",
            )
    note_plan_code = str(notes.get("plan_code") or "").strip().lower()
    if note_plan_code:
        metadata_bound = True
        try:
            note_plan_code = normalize_plan_code(note_plan_code)
        except InvalidPlanCodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay metadata plan_code is invalid.",
            ) from exc
        if note_plan_code != plan_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay metadata plan_code does not match the requested plan.",
            )

    return payment, order, order_ref, metadata_bound


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

    def razorpay_dashboard_url() -> str | None:
        url = (get_settings().RAZORPAY_DASHBOARD_URL or "").strip()
        return url or None

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
                "payment_provider": sub.payment_provider,
                "payment_customer_ref": sub.payment_customer_ref,
                "payment_subscription_ref": sub.payment_subscription_ref,
                "payment_request_ref": sub.payment_request_ref,
                "payment_dashboard_url": razorpay_dashboard_url()
                    if sub.payment_provider == "razorpay" else None,
                "updated_at": sub.updated_at,
            }
            for sub, project_name in rows
        ],
    }


@router.post("/billing/payments/confirm")
@limiter.limit("30/minute")
def owner_confirm_razorpay_payment(
    request: Request,
    body: OwnerBillingPaymentConfirmRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        plan_code = normalize_plan_code(body.plan_code)
    except InvalidPlanCodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if plan_code == "free":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="free cannot be confirmed as a paid Razorpay payment",
        )

    org_id = body.org_id.strip()
    payment_ref = body.payment_ref.strip()
    requested_order_ref = body.payment_request_ref.strip() if body.payment_request_ref else None
    if not org_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="org_id is required")
    if not payment_ref:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="payment_ref is required")

    existing_payment = db.scalar(
        select(Subscription).where(Subscription.payment_subscription_ref == payment_ref)
    )
    if existing_payment is not None and existing_payment.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="payment_ref is already linked to another org",
        )

    sub = db.scalar(select(Subscription).where(Subscription.org_id == org_id))
    if sub is None and existing_payment is not None:
        sub = existing_payment

    stored_order_ref = (
        requested_order_ref
        or (existing_payment.payment_request_ref if existing_payment is not None else None)
        or (sub.payment_request_ref if sub is not None else None)
    )
    payment, order, verified_order_ref, metadata_bound = _verify_owner_razorpay_payment(
        org_id=org_id,
        plan_code=plan_code,
        payment_ref=payment_ref,
        requested_order_ref=requested_order_ref,
        stored_order_ref=stored_order_ref,
    )

    if sub is None:
        sub = Subscription(
            org_id=org_id,
            plan_code=plan_code,
            status="active",
            seats=max(1, body.seats or 1),
            payment_provider="razorpay",
        )
        db.add(sub)
        db.flush()

    sub.payment_provider = "razorpay"
    sub.payment_subscription_ref = payment_ref
    if body.customer_ref:
        sub.payment_customer_ref = body.customer_ref.strip() or None
    elif payment.get("email"):
        sub.payment_customer_ref = str(payment.get("email") or "").strip() or None
    if verified_order_ref:
        sub.payment_request_ref = verified_order_ref
    if body.seats is not None:
        sub.seats = max(1, int(body.seats))
    sub.plan_code = plan_code
    sub.status = "active"
    sub.trial_end = None
    sub.current_period_end = body.current_period_end or (datetime.now(UTC) + timedelta(days=30))

    seed_plan_entitlements(db, org_id=org_id, plan_code=plan_code, commit=False)
    clear_trial_entitlements(db, org_id=org_id, commit=False)
    provider_event_id = f"owner_razorpay_confirm:{payment_ref}"
    existing_event = db.scalar(
        select(BillingEvent).where(
            BillingEvent.provider == "razorpay",
            BillingEvent.provider_event_id == provider_event_id,
        )
    )
    if existing_event is None:
        db.add(
            BillingEvent(
                provider="razorpay",
                provider_event_id=provider_event_id,
                event_type="payment.succeeded",
                provider_created_at=datetime.now(UTC),
                processed_at=datetime.now(UTC),
                result="applied",
                affected_org_id=org_id,
                payload_json=json.dumps(
                    {
                        "source": "owner_confirm",
                        "payment_id": payment_ref,
                        "order_id": verified_order_ref,
                        "plan_code": plan_code,
                        "org_id": org_id,
                        "payment_status": _razorpay_entity_status(payment),
                        "order_status": _razorpay_entity_status(order),
                        "metadata_bound": metadata_bound,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )
    _owner_audit(
        db,
        action="owner.billing.razorpay_payment.confirm",
        actor=_resolve_actor(request),
        target_id=org_id,
        metadata={
            "plan_code": plan_code,
            "payment_ref": payment_ref,
            "payment_request_ref": verified_order_ref,
            "current_period_end": sub.current_period_end,
            "provider_verified": True,
            "provider_metadata_bound": metadata_bound,
        },
    )
    db.commit()
    try:
        from app.services.entitlements_resolver import invalidate
        invalidate(org_id)
    except Exception:
        pass
    return {
        "ok": True,
        "org_id": org_id,
        "plan_code": sub.plan_code,
        "status": sub.status,
        "payment_provider": sub.payment_provider,
        "payment_subscription_ref": sub.payment_subscription_ref,
        "payment_request_ref": sub.payment_request_ref,
        "provider_verified": True,
        "provider_metadata_bound": metadata_bound,
        "current_period_end": sub.current_period_end,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
