# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""Artifact verification — validates HMAC-SHA256 signatures on signed artifact URLs.

Zero-trust rule: the worker never accepts an artifact without a valid signature
from the control plane.  The signing key is injected via environment variable
ARTIFACT_SIGNING_KEY and never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

logger = logging.getLogger(__name__)


def verify_artifact_signature(
    *,
    url: str,
    signature: str,
    signing_key: str,
    signature_required: bool = True,
) -> bool:
    """Return True when HMAC-SHA256(key, url) matches the provided signature."""
    if not signature:
        if signature_required:
            logger.error("Artifact signature missing while ARTIFACT_SIGNATURE_REQUIRED=true")
            return False
        logger.warning("Artifact signature missing — accepted only because signatures are explicitly disabled")
        return True
    if not signing_key:
        if signature_required:
            logger.error("ARTIFACT_SIGNING_KEY missing while ARTIFACT_SIGNATURE_REQUIRED=true")
            return False
        logger.warning("ARTIFACT_SIGNING_KEY missing — signature check skipped only because signatures are explicitly disabled")
        return True
    expected = hmac.new(
        signing_key.encode(),
        url.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def download_artifact(url: str, *, timeout: int = 30) -> bytes:
    """Download artifact bytes from a pre-signed URL."""
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content
