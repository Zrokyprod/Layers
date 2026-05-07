"""RFC 9116 security.txt and responsible-disclosure endpoints."""

from __future__ import annotations

import textwrap

from fastapi import APIRouter, Response

from app.core.config import get_settings

router = APIRouter(tags=["security"])


@router.get("/.well-known/security.txt")
def security_txt() -> Response:
    """Serve the machine-readable security.txt per RFC 9116."""
    settings = get_settings()
    contact = settings.SECURITY_CONTACT_EMAIL
    pgp = settings.SECURITY_PGP_KEY_URL
    policy = (
        f"{settings.APP_DOMAIN}/security"
        if getattr(settings, "APP_DOMAIN", "")
        else "/security"
    )

    encryption_line = f"Encryption: {pgp}\n" if pgp else ""
    body = textwrap.dedent(
        f"""\
        # Contact us about security issues — see our responsible-disclosure policy.
        Contact: mailto:{contact}
        Expires: 2030-01-01T00:00:00.000Z
        Preferred-Languages: en
        Policy: {policy}
        {encryption_line}
        # We appreciate responsible disclosure and will work with you to validate
        # and fix reported issues promptly.
        """
    ).strip() + "\n"

    return Response(
        content=body,
        media_type="text/plain",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


@router.get("/security")
def responsible_disclosure() -> dict:
    """Human-readable responsible-disclosure policy (JSON)."""
    settings = get_settings()
    return {
        "policy": "Responsible Disclosure",
        "contact": settings.SECURITY_CONTACT_EMAIL,
        "pgp_key_url": settings.SECURITY_PGP_KEY_URL,
        "acknowledgments_url": "/security/acknowledgments",
        "response_time": "We aim to acknowledge reports within 48 hours.",
        "scope": "Web application, API, SDK, and infrastructure.",
        "safe_harbor": "We will not take legal action against researchers who report vulnerabilities in good faith.",
    }


@router.get("/security/acknowledgments")
def security_acknowledgments() -> dict:
    """Hall of fame for security researchers."""
    return {
        "message": "Thank you to everyone who has responsibly disclosed security issues.",
        "acknowledgments": [],
        "how_to_report": "Submit findings to the contact listed in /.well-known/security.txt.",
    }
