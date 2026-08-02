from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SDK_PATH = ROOT / "zroky-sdk"
BACKEND_PATH = ROOT / "zroky-backend"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.stripe_refunds import refund_observation_state  # noqa: E402

STATE_PATH = Path(__file__).with_name(".silent_failure_demo_state.json")
WORKFLOW_KEY = "refund_flow_v1"
PACK_VERSION = "1.0.0"
SOURCE_BINDING = "stripe_refunds"
PLAYBOOK_KEY = "reissue_refund"
EXECUTOR_REF = "customer-recovery-executor://demo/stripe-refunds"
RUNNER_CREDENTIAL_REF = "customer-runner-secret://demo/stripe"
DEFAULT_AMOUNT_MINOR = 450_000
DEFAULT_CURRENCY = "inr"


@dataclass(frozen=True)
class DemoConfig:
    api_base: str
    dashboard_base: str
    project: str
    api_key: str
    admin_bearer_token: str | None
    stripe_secret_key: str
    stripe_secret_ref: str
    amount_minor: int
    currency: str
    use_project_header_context: bool

    @classmethod
    def from_env(cls) -> "DemoConfig":
        config = cls(
            api_base=os.environ.get("ZROKY_API_BASE", "https://api.zroky.com").rstrip("/"),
            dashboard_base=os.environ.get("ZROKY_DASHBOARD_URL", "https://app.zroky.com").rstrip("/"),
            project=_required("ZROKY_PROJECT"),
            api_key=_required("ZROKY_API_KEY"),
            admin_bearer_token=os.environ.get("ZROKY_ADMIN_BEARER_TOKEN")
            or os.environ.get("ZROKY_AUTH_TOKEN"),
            stripe_secret_key=_required("STRIPE_SECRET_KEY"),
            stripe_secret_ref=os.environ.get("ZROKY_STRIPE_SECRET_REF", "STRIPE_SECRET_KEY").strip(),
            amount_minor=int(os.environ.get("STRIPE_DEMO_AMOUNT_MINOR", str(DEFAULT_AMOUNT_MINOR))),
            currency=os.environ.get("STRIPE_DEMO_CURRENCY", DEFAULT_CURRENCY).strip().lower(),
            use_project_header_context=os.environ.get("ZROKY_USE_PROJECT_HEADER_CONTEXT") == "1",
        )
        if not config.stripe_secret_key.startswith(("sk_test_", "rk_test_")):
            raise SystemExit("Demo refuses to run with a live Stripe key. Use a test-mode key (sk_test_...).")
        return config


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required.")
    return value


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def demo_id() -> str:
    return "silent-failure-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def presenter_pause(message: str, *, auto: bool) -> None:
    print(f"\n{message}")
    if not auto:
        input("Press Enter to continue...")


class ApiClient:
    def __init__(self, config: DemoConfig) -> None:
        self.config = config

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        admin: bool = False,
        idempotency_key: str | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.api_base}{path}"
        if query:
            url += "?" + urlencode({key: value for key, value in query.items() if value is not None})
        headers = self._headers(admin=admin)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        raw = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=raw, headers=headers, method=method)
        try:
            with urlopen(request, timeout=45) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
        return json.loads(payload) if payload else {}

    def _headers(self, *, admin: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-project-id": self.config.project,
        }
        if admin and self.config.admin_bearer_token:
            headers["Authorization"] = f"Bearer {self.config.admin_bearer_token}"
            return headers
        if admin and self.config.use_project_header_context:
            return headers
        headers["x-api-key"] = self.config.api_key
        return headers


def stripe_request(
    config: DemoConfig,
    method: str,
    path: str,
    *,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    encoded = None if data is None else urlencode(data, doseq=True).encode("utf-8")
    auth = base64.b64encode(f"{config.stripe_secret_key}:".encode("utf-8")).decode("ascii")
    request = Request(
        f"https://api.stripe.com{path}",
        data=encoded,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Stripe {method} {path} failed: HTTP {exc.code} {detail}") from exc


def create_test_charge(config: DemoConfig, run_id: str) -> dict[str, Any]:
    if os.environ.get("STRIPE_DEMO_CHARGE_ID"):
        return stripe_request(config, "GET", f"/v1/charges/{os.environ['STRIPE_DEMO_CHARGE_ID']}")
    intent = stripe_request(
        config,
        "POST",
        "/v1/payment_intents",
        data={
            "amount": config.amount_minor,
            "currency": config.currency,
            "payment_method_types[]": "card",
            "payment_method": "pm_card_visa",
            "confirm": "true",
            "metadata[zroky_demo_id]": run_id,
        },
    )
    charge_id = str(intent.get("latest_charge") or "")
    if not charge_id:
        raise RuntimeError("Stripe PaymentIntent did not return latest_charge.")
    return stripe_request(config, "GET", f"/v1/charges/{charge_id}")


def refunds_for_charge(config: DemoConfig, charge_id: str) -> list[dict[str, Any]]:
    result = stripe_request(config, "GET", f"/v1/refunds?{urlencode({'charge': charge_id, 'limit': 10})}")
    rows = result.get("data")
    return rows if isinstance(rows, list) else []


def latest_refund_for_charge(config: DemoConfig, charge_id: str, *, timeout_seconds: int = 45) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        refunds = refunds_for_charge(config, charge_id)
        if refunds:
            return refunds[0]
        time.sleep(2)
    raise RuntimeError(f"No Stripe refund appeared for charge {charge_id}.")


def evidence_url(config: DemoConfig, graph_id: str | None = None) -> str:
    suffix = "/evidence" if not graph_id else f"/evidence?graph_id={graph_id}"
    return config.dashboard_base + suffix
