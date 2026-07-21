"""Connector capability manifest domain."""

from app.domain.connector_manifest.schema import (
    CONNECTOR_MANIFEST_SCHEMA_VERSION,
    ConnectorManifest,
    validate_connector_manifest,
)
from app.domain.connector_manifest.runtime import execute_connector_manifest_read

DOMAIN_MODULE = "connector_manifest"

__all__ = [
    "CONNECTOR_MANIFEST_SCHEMA_VERSION",
    "ConnectorManifest",
    "DOMAIN_MODULE",
    "execute_connector_manifest_read",
    "validate_connector_manifest",
]
