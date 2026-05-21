"""
Fix-strategy plugin registry.

Loads strategy callables via ``importlib.metadata`` entry points
(group ``zroky.fix_strategies``).  Falls back to built-ins when
the package is not installed.

Usage
-----
    from app.services.strategies._registry import load_fix_strategies
    strategies = load_fix_strategies()    # {name: callable}
    result = strategies["token_overflow"](request)
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _builtin_strategies() -> dict[str, Callable]:
    from app.services.strategies.token_overflow import generate as gen_token_overflow
    from app.services.strategies.loop_detected import generate as gen_loop_detected
    from app.services.strategies.rate_limit import generate as gen_rate_limit
    from app.services.strategies.auth_failure import generate as gen_auth_failure
    from app.services.strategies.cost_spike import generate as gen_cost_spike
    from app.services.strategies.generic import generate as gen_generic
    return {
        "token_overflow": gen_token_overflow,
        "loop_detected": gen_loop_detected,
        "rate_limit": gen_rate_limit,
        "auth_failure": gen_auth_failure,
        "cost_spike": gen_cost_spike,
        "generic": gen_generic,
    }


def load_fix_strategies() -> dict[str, Callable[..., Any]]:
    """Return registered fix-strategy callables keyed by entry-point name."""
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="zroky.fix_strategies")
        loaded: dict[str, Callable] = {}
        for ep in eps:
            try:
                loaded[ep.name] = ep.load()
            except Exception as exc:
                logger.warning("Failed to load strategy entry point %r: %s", ep.name, exc)
        if loaded:
            logger.debug("Loaded %d strategy(ies) from entry points: %s", len(loaded), list(loaded))
            return loaded
    except Exception as exc:
        logger.debug("importlib.metadata unavailable (%s); using built-in strategies", exc)

    logger.debug("No entry-point strategies registered; using built-in fallback registry")
    return _builtin_strategies()
