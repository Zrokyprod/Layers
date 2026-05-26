"""Compatibility aggregator for owner/admin routes."""

from app.api.routes._internal.owner_common import router
from app.api.routes._internal.owner_health import *
from app.api.routes._internal.owner_pricing_audit import *
from app.api.routes._internal.owner_users_projects import *
from app.api.routes._internal.owner_rate_audit_llm import *
from app.api.routes._internal.owner_support_billing import *
from app.api.routes._internal.owner_operations import *
