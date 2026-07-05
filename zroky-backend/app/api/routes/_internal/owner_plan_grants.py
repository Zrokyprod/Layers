"""Owner-console plan override — double-verified free→paid grants.

Two independent factors on top of the admin/provisioning session:

  A. A fresh step-up OTP challenge (6-digit code, single-use, 5-min TTL).
  B. A typed confirmation of the target org before the grant commits.

Every grant re-seeds `source='plan'` entitlements, invalidates the resolver
cache, and writes an `owner.plan.override` audit row. Mirrors the transition
machinery in `subscription_lifecycle._transition_to_free`.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.api.routes._internal.owner_common import *  # noqa: F401,F403 — router, deps, models, redis
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor
from app.services import entitlements_resolver
from app.services.billing_plans import normalize_plan_code
from app.services.email_sender import send_email
from app.services.entitlements import seed_plan_entitlements

_CHALLENGE_TTL_SECONDS = 300
_CHALLENGE_KEY_PREFIX = "zroky:owner:plan_grant_challenge:"
_GRANTABLE_PLAN_CODES: tuple[str, ...] = ("free", "starter", "pro")
_DURATION_KINDS: tuple[str, ...] = ("permanent", "comp_30d", "comp_90d")
_AUDIT_ACTION = "owner.plan.override"

# In-memory fallback store so the flow works (and is testable) without Redis.
# Prod with Redis uses Redis so challenge+commit survive across workers.
_MEM_CHALLENGES: dict[str, tuple[float, dict[str, Any]]] = {}


# ─── challenge store (Redis when available, in-memory fallback) ────────────────


def _is_production() -> bool:
    return get_settings().APP_ENV == "production"


def _challenge_store_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Owner plan grant challenge store unavailable.",
    )


def _store_challenge(challenge_id: str, record: dict[str, Any]) -> None:
    if _redis_ok():
        try:
            get_redis_client().setex(
                _CHALLENGE_KEY_PREFIX + challenge_id,
                _CHALLENGE_TTL_SECONDS,
                json.dumps(record, default=str),
            )
            return
        except Exception as exc:
            if _is_production():
                raise _challenge_store_unavailable() from exc
    if _is_production():
        raise _challenge_store_unavailable()
    _MEM_CHALLENGES[challenge_id] = (time.time() + _CHALLENGE_TTL_SECONDS, record)


def _load_challenge(challenge_id: str) -> dict[str, Any] | None:
    if _redis_ok():
        try:
            raw = get_redis_client().get(_CHALLENGE_KEY_PREFIX + challenge_id)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            if _is_production():
                raise _challenge_store_unavailable() from exc
    if _is_production():
        raise _challenge_store_unavailable()
    entry = _MEM_CHALLENGES.get(challenge_id)
    if entry is None:
        return None
    expiry_ts, record = entry
    if time.time() > expiry_ts:
        _MEM_CHALLENGES.pop(challenge_id, None)
        return None
    return record


def _delete_challenge(challenge_id: str) -> None:
    if _redis_ok():
        try:
            get_redis_client().delete(_CHALLENGE_KEY_PREFIX + challenge_id)
            if _is_production():
                return
        except Exception as exc:
            if _is_production():
                raise _challenge_store_unavailable() from exc
    if _is_production():
        raise _challenge_store_unavailable()
    _MEM_CHALLENGES.pop(challenge_id, None)


def _validate_plan(target_plan_code: str) -> str:
    try:
        normalized = normalize_plan_code(target_plan_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized not in _GRANTABLE_PLAN_CODES:
        raise HTTPException(
            status_code=422,
            detail=f"target_plan_code must be one of: {list(_GRANTABLE_PLAN_CODES)}",
        )
    return normalized


def _current_plan_code(db: Session, org_id: str) -> str | None:
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org_id))
    return sub.plan_code if sub else None


# ─── request/response schemas ─────────────────────────────────────────────────


class PlanGrantChallengeRequest(BaseModel):
    org_id: str
    target_plan_code: str


class PlanGrantChallengeResponse(BaseModel):
    challenge_id: str
    expires_at: datetime
    org_id: str
    current_plan_code: str | None
    target_plan_code: str
    delivery: str
    dev_code: str | None = None


class PlanGrantCommitRequest(BaseModel):
    challenge_id: str
    code: str
    typed_confirmation: str
    org_id: str
    target_plan_code: str
    reason: str
    duration_kind: str = "permanent"


class PlanGrantCommitResponse(BaseModel):
    ok: bool
    org_id: str
    previous_plan_code: str | None
    plan_code: str
    duration_kind: str
    granted_at: datetime


class PlanGrantAuditItem(BaseModel):
    id: str
    actor: str | None
    org_id: str
    previous_plan_code: str | None
    plan_code: str | None
    reason: str | None
    duration_kind: str | None
    created_at: datetime


class PlanGrantAuditResponse(BaseModel):
    items: list[PlanGrantAuditItem]


# ─── endpoints ────────────────────────────────────────────────────────────────


@router.post("/plan-grants/challenge", response_model=PlanGrantChallengeResponse)
@limiter.limit("5/minute")
def owner_plan_grant_challenge(
    request: Request,
    body: PlanGrantChallengeRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> PlanGrantChallengeResponse:
    target = _validate_plan(body.target_plan_code)
    current_plan = _current_plan_code(db, body.org_id)

    challenge_id = uuid4().hex
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(UTC)
    actor = _resolve_actor(request)
    _store_challenge(
        challenge_id,
        {
            "actor": actor,
            "org_id": body.org_id,
            "target_plan_code": target,
            "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "created_at": now.isoformat(),
        },
    )

    settings = get_settings()
    is_prod = settings.APP_ENV == "production"
    delivery = "response"
    if is_prod:
        if not _email_owner_code(db, actor_subject=actor, code=code, org_id=body.org_id, target=target):
            _delete_challenge(challenge_id)
            raise HTTPException(
                status_code=503,
                detail="Owner verification code could not be delivered.",
            )
        delivery = "email"

    return PlanGrantChallengeResponse(
        challenge_id=challenge_id,
        expires_at=now + timedelta(seconds=_CHALLENGE_TTL_SECONDS),
        org_id=body.org_id,
        current_plan_code=current_plan,
        target_plan_code=target,
        delivery=delivery,
        dev_code=None if (is_prod and delivery == "email") else code,
    )


@router.post("/plan-grants", response_model=PlanGrantCommitResponse)
@limiter.limit("10/minute")
def owner_plan_grant_commit(
    request: Request,
    body: PlanGrantCommitRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> PlanGrantCommitResponse:
    target = _validate_plan(body.target_plan_code)

    if body.duration_kind not in _DURATION_KINDS:
        raise HTTPException(status_code=422, detail=f"duration_kind must be one of: {list(_DURATION_KINDS)}")

    # ── Factor A: fresh step-up OTP challenge (single-use, TTL'd) ──
    record = _load_challenge(body.challenge_id)
    if record is None:
        raise HTTPException(status_code=401, detail="Verification code expired or not found. Request a new one.")

    provided_hash = hashlib.sha256(body.code.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(provided_hash, str(record.get("code_hash", ""))):
        raise HTTPException(status_code=401, detail="Invalid verification code.")

    # Challenge must be for exactly this target — no cross-target reuse.
    if str(record.get("org_id")) != body.org_id or str(record.get("target_plan_code")) != target:
        raise HTTPException(status_code=422, detail="Verification code does not match this org and plan.")

    # ── Factor B: typed confirmation of the target org ──
    sub = db.scalar(select(Subscription).where(Subscription.org_id == body.org_id))
    project = db.scalar(select(Project).where(Project.id == body.org_id))
    if not _typed_confirmation_matches(body.typed_confirmation, org_id=body.org_id, sub=sub, project=project):
        raise HTTPException(
            status_code=422,
            detail="Typed confirmation does not match the target org. Type the org id or billing email exactly.",
        )

    # ── Apply: flip plan, re-seed entitlements, audit, commit ──
    _delete_challenge(body.challenge_id)

    previous_plan = sub.plan_code if sub else None
    now = datetime.now(UTC)

    if sub is None:
        sub = Subscription(
            id=str(uuid4()),
            org_id=body.org_id,
            payment_provider="manual_grant",
            plan_code=target,
            status="active",
        )
        db.add(sub)
    else:
        sub.plan_code = target
        sub.status = "active"
        db.add(sub)

    if body.duration_kind == "comp_30d":
        sub.current_period_end = now + timedelta(days=30)
    elif body.duration_kind == "comp_90d":
        sub.current_period_end = now + timedelta(days=90)

    seed_plan_entitlements(db, org_id=body.org_id, plan_code=target, commit=False)

    _owner_audit(
        db,
        action=_AUDIT_ACTION,
        actor=_resolve_actor(request),
        target_id=body.org_id,
        metadata={
            "org_id": body.org_id,
            "previous_plan_code": previous_plan,
            "plan_code": target,
            "reason": body.reason,
            "duration_kind": body.duration_kind,
            "challenge_id": body.challenge_id,
        },
    )
    db.commit()

    # Drop the stale resolver cache after the committed entitlement re-seed.
    try:
        entitlements_resolver.invalidate(body.org_id)
    except Exception:
        pass

    return PlanGrantCommitResponse(
        ok=True,
        org_id=body.org_id,
        previous_plan_code=previous_plan,
        plan_code=target,
        duration_kind=body.duration_kind,
        granted_at=now,
    )


@router.get("/plan-grants/audit", response_model=PlanGrantAuditResponse)
def owner_plan_grant_audit(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    org_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> PlanGrantAuditResponse:
    rows = db.execute(
        select(AuditLog)
        .where(AuditLog.action == _AUDIT_ACTION)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    ).scalars().all()

    items: list[PlanGrantAuditItem] = []
    for row in rows:
        try:
            meta = json.loads(row.metadata_json or "{}")
        except Exception:
            meta = {}
        row_org = str(meta.get("org_id") or meta.get("target_id") or "")
        if org_id and row_org != org_id:
            continue
        items.append(
            PlanGrantAuditItem(
                id=row.id,
                actor=row.actor_subject,
                org_id=row_org,
                previous_plan_code=meta.get("previous_plan_code"),
                plan_code=meta.get("plan_code"),
                reason=meta.get("reason"),
                duration_kind=meta.get("duration_kind"),
                created_at=row.created_at,
            )
        )
        if len(items) >= limit:
            break

    return PlanGrantAuditResponse(items=items)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _typed_confirmation_matches(
    typed: str,
    *,
    org_id: str,
    sub: "Subscription | None",
    project: "Project | None",
) -> bool:
    candidate = (typed or "").strip().lower()
    if not candidate:
        return False
    accepted = {org_id.strip().lower()}
    if project is not None and project.name:
        accepted.add(project.name.strip().lower())
    if sub is not None and sub.payment_customer_ref:
        accepted.add(sub.payment_customer_ref.strip().lower())
    return candidate in accepted


def _email_owner_code(
    db: Session,
    *,
    actor_subject: str,
    code: str,
    org_id: str,
    target: str,
) -> bool:
    owner = db.scalar(select(User).where(User.id == actor_subject))
    recipient = owner.email if owner and owner.email else None
    if not recipient:
        return False
    subject = "Zroky owner console — plan grant verification code"
    body = (
        f"Verification code: {code}\n\n"
        f"Target org: {org_id}\nTarget plan: {target}\n\n"
        "This code expires in 5 minutes and can be used once. "
        "If you did not request this, ignore this email."
    )
    try:
        return bool(send_email([recipient], subject, f"<pre>{body}</pre>", plain_body=body))
    except Exception:
        return False


__all__ = [name for name in globals() if not name.startswith("__")]
