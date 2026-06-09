from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.services.github_webhooks import process_github_webhook_event

router = APIRouter(prefix="/v1/integrations/github")
_UNSIGNED_WEBHOOK_DEV_ENVS = {"dev", "development", "local", "test", "testing"}


def _verify_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = (get_settings().GITHUB_WEBHOOK_SECRET or "").strip()
    if not secret:
        return get_settings().APP_ENV.strip().lower() in _UNSIGNED_WEBHOOK_DEV_ENVS
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    raw_body = await request.body()
    if not _verify_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub webhook signature")

    if not x_github_event:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-GitHub-Event header")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GitHub webhook JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub webhook payload must be an object")

    result = process_github_webhook_event(
        db,
        event_name=x_github_event,
        payload=payload,
        delivery_id=x_github_delivery,
    )
    return {
        "status": "ok",
        **result,
    }
