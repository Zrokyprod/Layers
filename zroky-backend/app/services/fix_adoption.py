"""Compatibility module for fix adoption services."""

import sys

from app.services._internal import fix_adoption_impl as _impl

sys.modules[__name__] = _impl
