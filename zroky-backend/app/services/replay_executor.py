"""Compatibility module for replay execution services."""

import sys

from app.services._internal import replay_executor_impl as _impl

sys.modules[__name__] = _impl
