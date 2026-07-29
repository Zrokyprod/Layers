"""Connector capability manifest domain."""

from app.domain.connector_manifest.schema import (
    CONNECTOR_MANIFEST_SCHEMA_VERSION,
    ConnectorManifest,
    validate_connector_manifest,
)
from app.domain.connector_manifest.runtime import execute_connector_manifest_read
from app.domain.connector_manifest.presets import (
    CONNECTOR_MANIFEST_PRESETS,
    get_connector_manifest_preset,
)

DOMAIN_MODULE = "connector_manifest"

__all__ = [
    "CONNECTOR_MANIFEST_SCHEMA_VERSION",
    "CONNECTOR_MANIFEST_PRESETS",
    "ConnectorManifest",
    "DOMAIN_MODULE",
    "execute_connector_manifest_read",
    "get_connector_manifest_preset",
    "validate_connector_manifest",
]
