"""Outcome graph and verification domain."""

DOMAIN_MODULE = "outcome_graph"

from app.domain.outcome_graph.builder import build_outcome_graph_snapshot, classify_outcome_graph_snapshot

__all__ = ["DOMAIN_MODULE", "build_outcome_graph_snapshot", "classify_outcome_graph_snapshot"]
