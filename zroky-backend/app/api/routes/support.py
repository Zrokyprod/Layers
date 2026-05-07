from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.tenant import require_tenant_context, TenantContext
from app.db.models import SupportMessage, SupportTicket
from app.db.session import get_db_session
from app.schemas.support import (
    SupportMessageCreateRequest,
    SupportMessageItem,
    SupportTicketCreateRequest,
    SupportTicketDetailResponse,
    SupportTicketItem,
    SupportTicketListResponse,
    SupportTicketUpdateRequest,
)

router = APIRouter(prefix="/v1/support")


def _ticket_to_item(ticket: SupportTicket) -> SupportTicketItem:
    return SupportTicketItem(
        ticket_id=ticket.id,
        tenant_id=ticket.tenant_id,
        user_id=ticket.user_id,
        subject=ticket.subject,
        email=ticket.email,
        title=ticket.title,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        assigned_to=ticket.assigned_to,
        resolved_at=ticket.resolved_at,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        message_count=len(ticket.messages),
    )


def _message_to_item(msg: SupportMessage) -> SupportMessageItem:
    return SupportMessageItem(
        message_id=msg.id,
        sender_type=msg.sender_type,
        sender_subject=msg.sender_subject,
        body=msg.body,
        is_internal=msg.is_internal,
        created_at=msg.created_at,
    )


@router.post("/tickets", response_model=SupportTicketItem, status_code=status.HTTP_201_CREATED)
def create_ticket(
    body: SupportTicketCreateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SupportTicketItem:
    ticket = SupportTicket(
        tenant_id=context.tenant_id,
        subject=context.subject,
        title=body.title,
        description=body.description,
        category=body.category,
        priority=body.priority,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return _ticket_to_item(ticket)


@router.get("/tickets", response_model=SupportTicketListResponse)
def list_tickets(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> SupportTicketListResponse:
    q = select(SupportTicket).where(SupportTicket.tenant_id == tenant_id)
    count_q = select(func.count()).select_from(SupportTicket).where(SupportTicket.tenant_id == tenant_id)
    if status:
        q = q.where(SupportTicket.status == status)
        count_q = count_q.where(SupportTicket.status == status)
    q = q.order_by(SupportTicket.created_at.desc())
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return SupportTicketListResponse(
        items=[_ticket_to_item(r) for r in rows],
        total=total,
    )


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailResponse)
def get_ticket(
    ticket_id: str,
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> SupportTicketDetailResponse:
    ticket = db.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .where(SupportTicket.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return SupportTicketDetailResponse(
        ticket=_ticket_to_item(ticket),
        messages=[_message_to_item(m) for m in ticket.messages if not m.is_internal],
    )


@router.patch("/tickets/{ticket_id}", response_model=SupportTicketItem)
def update_ticket(
    ticket_id: str,
    body: SupportTicketUpdateRequest,
    tenant_id: str = Depends(require_project_role("admin")),
    db: Session = Depends(get_db_session),
) -> SupportTicketItem:
    ticket = db.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .where(SupportTicket.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    if body.status is not None:
        ticket.status = body.status
        if body.status == "resolved" and ticket.resolved_at is None:
            from datetime import datetime, timezone
            ticket.resolved_at = datetime.now(timezone.utc)
    if body.priority is not None:
        ticket.priority = body.priority
    if body.assigned_to is not None:
        ticket.assigned_to = body.assigned_to

    db.commit()
    db.refresh(ticket)
    return _ticket_to_item(ticket)


@router.post("/tickets/{ticket_id}/messages", response_model=SupportMessageItem, status_code=status.HTTP_201_CREATED)
def add_message(
    ticket_id: str,
    body: SupportMessageCreateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SupportMessageItem:
    ticket = db.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .where(SupportTicket.tenant_id == context.tenant_id)
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    msg = SupportMessage(
        ticket_id=ticket.id,
        sender_type="user",
        sender_subject=context.subject,
        body=body.body,
        is_internal=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _message_to_item(msg)
