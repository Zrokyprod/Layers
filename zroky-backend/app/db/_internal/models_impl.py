"""Compatibility aggregator for SQLAlchemy model definitions.

The public import path remains ``app.db.models``. Concrete model classes live
in semantic modules so future edits do not require touching one giant file.
"""

from app.db._internal.model_shared import compute_email_hash
from app.db._internal.model_diagnosis import *
from app.db._internal.model_identity import *
from app.db._internal.model_runtime import *
from app.db._internal.model_goldens import *
from app.db._internal.model_growth import *
from app.db._internal.model_provider_drift import *
from app.db._internal.model_reliability import *
