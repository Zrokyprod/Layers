"""Connector capability manifest domain."""

from app.domain.connector_manifest.schema import (
    CONNECTOR_MANIFEST_SCHEMA_VERSION,
    ConnectorManifest,
    validate_connector_manifest,
)

DOMAIN_MODULE = "connector_manifest"

__all__ = [
    "CONNECTOR_MANIFEST_SCHEMA_VERSION",
    "ConnectorManifest",
    "DOMAIN_MODULE",
    "validate_connector_manifest",
]
