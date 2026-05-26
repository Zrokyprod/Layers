"""Compatibility module for owner/admin routes."""

import sys

from app.api.routes._internal import owner_impl as _impl

sys.modules[__name__] = _impl
