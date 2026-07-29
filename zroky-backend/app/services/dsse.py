from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.services.action_receipts import _ed25519_private_key


DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"


def pae(payload_type: str, payload: bytes) -> bytes:
    payload_type_bytes = payload_type.encode("utf-8")
    return b" ".join(
        [
            b"DSSEv1",
            str(len(payload_type_bytes)).encode("ascii"),
            payload_type_bytes,
            str(len(payload)).encode("ascii"),
            payload,
        ]
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")


def sign_envelope(statement: dict[str, Any]) -> dict[str, Any]:
    payload = canonical_json_bytes(statement)
    private_key, key_id = _ed25519_private_key()
    signature = private_key.sign(pae(DSSE_PAYLOAD_TYPE, payload))
    return {
        "payloadType": DSSE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [{"keyid": key_id, "sig": base64.b64encode(signature).decode("ascii")}],
    }


def verify_envelope(envelope: dict[str, Any], public_key_b64: str) -> dict[str, Any]:
    try:
        payload_type = str(envelope["payloadType"])
        payload = base64.b64decode(str(envelope["payload"]), validate=True)
        signatures = envelope["signatures"]
        if not isinstance(signatures, list) or not signatures:
            raise ValueError("missing signature")
        signature = base64.b64decode(str(signatures[0]["sig"]), validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64.strip(), validate=True))
        public_key.verify(signature, pae(payload_type, payload))
        return json.loads(payload.decode("utf-8"))
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise ValueError("TAMPERED/INVALID") from exc
