from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from zroky.attestation import verify_attestation
from zroky.verify_attestation import main as verify_attestation_main


def _export(statement: dict) -> tuple[dict, str]:
    payload = json.dumps(statement, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_type = "application/vnd.in-toto+json"
    key = Ed25519PrivateKey.generate()
    sig = key.sign(
        b" ".join([b"DSSEv1", b"28", payload_type.encode(), str(len(payload)).encode(), payload])
    )
    public_key = base64.b64encode(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [{"keyid": "test", "sig": base64.b64encode(sig).decode("ascii")}],
    }, public_key


def test_verify_attestation_roundtrip() -> None:
    envelope, public_key = _export({"_type": "https://in-toto.io/Statement/v1", "subject": []})

    assert verify_attestation(envelope, public_key)["subject"] == []


def test_verify_attestation_rejects_tampered_payload() -> None:
    envelope, public_key = _export({"subject": []})
    envelope["payload"] = base64.b64encode(b'{"subject":["changed"]}').decode("ascii")

    with pytest.raises(ValueError, match="TAMPERED/INVALID"):
        verify_attestation(envelope, public_key)


def test_verify_attestation_cli_accepts_export_and_rejects_tamper(tmp_path: Path) -> None:
    envelope, public_key = _export({"subject": []})
    export_path = tmp_path / "export.json"
    export_path.write_text(
        json.dumps({"attestation": envelope, "public_key": {"public_key": public_key}}),
        encoding="utf-8",
    )
    assert verify_attestation_main([str(export_path)]) == 0

    envelope["payload"] = base64.b64encode(b'{"subject":["changed"]}').decode("ascii")
    export_path.write_text(
        json.dumps({"attestation": envelope, "public_key": {"public_key": public_key}}),
        encoding="utf-8",
    )
    assert verify_attestation_main([str(export_path)]) == 1
