from __future__ import annotations

import base64

import pytest

from app.services.action_receipts import action_receipt_public_key_payload
from app.services.dsse import pae, sign_envelope, verify_envelope


def test_pae_matches_dsse_spec_vector() -> None:
    assert pae("http://example.com/HelloWorld", b"hello world") == b"DSSEv1 29 http://example.com/HelloWorld 11 hello world"


def test_dsse_sign_verify_roundtrip_and_tamper_rejection() -> None:
    envelope = sign_envelope({"subject": [{"name": "outcome-graph/1"}]})
    public_key = action_receipt_public_key_payload()["public_key"]

    assert verify_envelope(envelope, public_key)["subject"][0]["name"] == "outcome-graph/1"

    envelope["payload"] = base64.b64encode(b'{"subject":[{"name":"changed"}]}').decode("ascii")
    with pytest.raises(ValueError, match="TAMPERED/INVALID"):
        verify_envelope(envelope, public_key)


def test_dsse_rejects_wrong_public_key() -> None:
    envelope = sign_envelope({"subject": []})
    wrong_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    with pytest.raises(ValueError, match="TAMPERED/INVALID"):
        verify_envelope(envelope, wrong_key)
