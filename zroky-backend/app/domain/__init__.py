"""Final Zroky domain package.

This package is the target home for product domain code. Keep HTTP routes,
database wiring, queue workers, and vendor adapters outside this layer.
"""

FINAL_DOMAIN_MODULES = (
    "intent",
    "policy",
    "approval",
    "assurance_pack",
    "connector_manifest",
    "observation",
    "outcome_graph",
    "incident",
    "recovery",
    "evidence",
    "tenancy",
)
