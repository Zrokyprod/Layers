# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""
_globals.py — intentionally minimal.

All SDK state (model_health_registry, rate_limiter, response_cache, …) lives
as module-level attributes of zroky.__init__.  Submodules access them via:

    import zroky as _z   # lazy, inside function bodies only
    _z._model_health_registry.record(...)

This avoids the synchronisation problem where test fixtures that do
    zroky._model_health_registry = ModelHealthRegistry()
would be invisible to any submodule holding its own reference.
"""
