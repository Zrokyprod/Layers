from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Literal

from app.db.models import Call

BASE_CURRENCY = "USD"
TOKEN_UNIT = "tokens"
SUPPORTED_DISPLAY_CURRENCIES = {"USD"}
DISPLAY_DECIMAL_PLACES = 2
EXCHANGE_RATE_DECIMAL_PLACES = 8
DISPLAY_ROUNDING_MODE = "HALF_UP"
CURRENCY_SYMBOLS = {"USD": "$"}
DisplayCurrency = Literal["USD"]


@dataclass(frozen=True)
class CurrencyDisplayContext:
    requested_display_currency: DisplayCurrency
    display_currency: DisplayCurrency
    exchange_rate_used: float | None = None
    exchange_rate_timestamp: str | None = None
    exchange_rate_source: str | None = None
    exchange_rates_mixed: bool = False
    missing_exchange_rate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "display_currency": self.display_currency,
            "display_currency_code": self.display_currency,
            "display_currency_symbol": CURRENCY_SYMBOLS[self.display_currency],
            "requested_display_currency": self.requested_display_currency,
            "exchange_rate_used": None,
            "exchange_rate_timestamp": None,
            "exchange_rate_source": None,
            "exchange_rates_mixed": False,
            "display_decimal_places": DISPLAY_DECIMAL_PLACES,
            "display_rounding_mode": DISPLAY_ROUNDING_MODE,
            "exchange_rate_decimal_places": EXCHANGE_RATE_DECIMAL_PLACES,
            "cost_currency": BASE_CURRENCY,
            "token_unit": TOKEN_UNIT,
        }


def normalize_display_currency(value: str | None) -> DisplayCurrency:
    return "USD"


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return as_utc(dt).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        return datetime.fromtimestamp(float(candidate), tz=timezone.utc)
    except ValueError:
        pass

    if len(candidate) == 10 and candidate.count("-") == 2:
        candidate = f"{candidate}T00:00:00+00:00"
    elif candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    return as_utc(parsed)


def as_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed > 0 else None


def _quantize_decimal(value: Decimal, places: int) -> Decimal:
    quantizer = Decimal("1").scaleb(-places)
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def rounded_exchange_rate(value: Any) -> float | None:
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    return float(_quantize_decimal(parsed, EXCHANGE_RATE_DECIMAL_PLACES))


def rounded_display_amount(value: Any) -> float:
    parsed = _to_decimal(value)
    if parsed is None:
        return 0.0
    return float(_quantize_decimal(parsed, DISPLAY_DECIMAL_PLACES))


# ── USD-only stubs ─────────────────────────────────────────────────────────────
# INR display currency and live exchange-rate fetching are deferred.
# All public function signatures are preserved so callers need no changes.


def resolve_ingest_exchange_rate(
    payload: dict[str, Any],
    *,
    captured_at: datetime,
) -> dict[str, Any]:
    """USD-only stub. Always returns null exchange rate fields."""
    return {
        "exchange_rate_usd_to_inr": None,
        "exchange_rate_timestamp": None,
        "exchange_rate_source": None,
    }


def build_currency_context(
    calls: Iterable[Call],
    requested_display_currency: str | None,
) -> CurrencyDisplayContext:
    """USD-only stub. Always returns a USD display context."""
    return CurrencyDisplayContext(
        requested_display_currency="USD",
        display_currency="USD",
    )


def convert_usd_amount(
    amount_usd: float,
    *,
    call: Call | None = None,
    context: CurrencyDisplayContext,
) -> float:
    return rounded_display_amount(amount_usd)


def aggregate_display_total(
    calls: Iterable[Call],
    amount_selector: Callable[[Call], float],
    *,
    context: CurrencyDisplayContext,
) -> float:
    total = Decimal("0")
    for call in calls:
        total += _to_decimal(amount_selector(call)) or Decimal("0")
    return rounded_display_amount(total)


def append_confidence_reason(base_reason: str | None, reason: str) -> str:
    if not base_reason:
        return reason
    parts = [part.strip() for part in base_reason.split(";") if part.strip()]
    if reason not in parts:
        parts.append(reason)
    return ";".join(parts)


def get_exchange_rate_debug_snapshot() -> dict[str, Any]:
    """Return a diagnostic snapshot of the exchange-rate cache state.

    Used by the owner /infrastructure endpoint to show whether the currency
    cache is usable, stale, or unreachable.
    """
    return {
        "cache_is_usable": True,
        "cache_is_stale": False,
        "base_currency": "USD",
        "cached_rates_count": 0,
        "source": "static_usd_only",
    }
