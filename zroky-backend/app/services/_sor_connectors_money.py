from __future__ import annotations

from app.services._sor_connectors_core import *  # noqa: F403


def _decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite():
            return None
    except (InvalidOperation, OverflowError, ValueError):
        return None
    return amount


def _currency_exponent(currency: Any) -> int:
    if not isinstance(currency, str):
        return 2
    normalized = currency.strip().upper()
    if normalized in _ZERO_DECIMAL_CURRENCIES:
        return 0
    if normalized in _THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def _minor_to_major_text(value: Any, *, currency: Any = None) -> str | None:
    amount = _decimal_value(value)
    if amount is None:
        return None
    exponent = _currency_exponent(currency)
    divisor = Decimal(10) ** exponent
    major = amount / divisor
    return format(major.normalize(), "f")


def _major_to_minor_int(value: Any, *, currency: Any = None) -> int | None:
    amount = _decimal_value(value)
    if amount is None:
        return None
    exponent = _currency_exponent(currency)
    minor = amount * (Decimal(10) ** exponent)
    if minor != minor.to_integral_value():
        return None
    return int(minor)


def _minor_units_int(value: Any) -> int | None:
    amount = _decimal_value(value)
    if amount is None or amount != amount.to_integral_value():
        return None
    return int(amount)


def _legacy_usd_from_minor(value: Any, *, currency: Any = None) -> float | None:
    if isinstance(currency, str) and currency.strip().upper() not in {"", "USD"}:
        return None
    major = _minor_to_major_text(value, currency="USD")
    if major is None:
        return None
    return float(Decimal(major))


def _set_money_from_minor_units(
    normalized: dict[str, Any],
    value: Any,
    *,
    currency: Any = None,
    legacy_usd_alias: bool = True,
) -> None:
    minor = _minor_units_int(value)
    if minor is None:
        return
    normalized["amount_minor"] = minor
    major = _minor_to_major_text(minor, currency=currency or normalized.get("currency"))
    if major is not None:
        normalized["amount_major"] = major
    if legacy_usd_alias and "amount_usd" not in normalized:
        usd_value = _legacy_usd_from_minor(minor, currency=currency or normalized.get("currency"))
        if usd_value is not None:
            normalized["amount_usd"] = usd_value


def _set_money_from_major_units(
    normalized: dict[str, Any],
    value: Any,
    *,
    currency: Any = None,
    legacy_usd_alias: bool = True,
) -> None:
    amount = _decimal_value(value)
    if amount is None:
        return
    normalized["amount_major"] = format(amount.normalize(), "f")
    minor = _major_to_minor_int(amount, currency=currency or normalized.get("currency"))
    if minor is not None:
        normalized["amount_minor"] = minor
    if legacy_usd_alias and "amount_usd" not in normalized:
        if not isinstance(currency, str) or currency.strip().upper() in {"", "USD"}:
            normalized["amount_usd"] = float(amount)


def _cents_to_usd(value: Any) -> float | None:
    return _legacy_usd_from_minor(value, currency="USD")


__all__ = [name for name in globals() if not name.startswith("__")]
