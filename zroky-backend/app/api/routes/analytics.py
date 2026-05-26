"""Compatibility module for analytics routes."""

import sys

from app.api.routes._internal import analytics_impl as _impl

sys.modules[__name__] = _impl
