"""Compatibility module for Celery tasks.

The task implementations moved internal, but every task keeps its explicit
``app.worker.tasks.*`` Celery name.
"""

import sys

from app.worker._internal import tasks_impl as _impl

sys.modules[__name__] = _impl
