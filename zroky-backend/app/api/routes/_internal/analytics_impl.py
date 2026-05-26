"""Compatibility aggregator for analytics routes."""

from app.api.routes._internal.analytics_common import router
from app.api.routes._internal.analytics_summary import *
from app.api.routes._internal.analytics_activity import *
from app.api.routes._internal.analytics_cost_trends import *
from app.api.routes._internal.analytics_budget import *
from app.api.routes._internal.analytics_cost_agents import *
from app.api.routes._internal.analytics_loops import *
from app.api.routes._internal.analytics_auth import *
from app.api.routes._internal.analytics_traces import *
from app.api.routes._internal.analytics_savings import *
