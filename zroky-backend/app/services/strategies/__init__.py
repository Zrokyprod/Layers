"""
Fix strategy registry.

Each module exposes a ``generate(request) -> FixTuple`` callable.
The orchestrator (fix_generator.generate_fix_suggestion) dispatches here.
"""
from __future__ import annotations

from app.services.strategies.ai_fix import FixTuple, _ai_fix
from app.services.strategies.token_overflow import generate as generate_token_overflow
from app.services.strategies.loop_detected import generate as generate_loop_detected
from app.services.strategies.rate_limit import generate as generate_rate_limit
from app.services.strategies.auth_failure import generate as generate_auth_failure
from app.services.strategies.cost_spike import generate as generate_cost_spike
from app.services.strategies.generic import generate as generate_generic

__all__ = [
    "FixTuple",
    "_ai_fix",
    "generate_token_overflow",
    "generate_loop_detected",
    "generate_rate_limit",
    "generate_auth_failure",
    "generate_cost_spike",
    "generate_generic",
]
