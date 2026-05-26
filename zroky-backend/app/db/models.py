"""Compatibility module for SQLAlchemy models."""

import sys

from app.db._internal import models_impl as _impl

sys.modules[__name__] = _impl
