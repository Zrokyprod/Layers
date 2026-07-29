"""Outcome incident domain."""

DOMAIN_MODULE = "incident"

from app.domain.incident.builder import build_incident_from_outcome_graph

__all__ = ["DOMAIN_MODULE", "build_incident_from_outcome_graph"]
