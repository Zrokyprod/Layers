"""Canonicalize private runner credential references.

Revision ID: 0125_canonicalize_private_runner_refs
Revises: 0124_connector_credential_custody
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op


revision = "0125_canonicalize_private_runner_refs"
down_revision = "0124_connector_credential_custody"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``runner://`` was accepted briefly by the initial custody API but is not
    # understood by the customer-hosted runner. Preserve the opaque path while
    # moving records to the runner's documented, allowlisted protocol.
    op.execute(
        """
        UPDATE connector_credentials
        SET secret_ref = 'customer-runner-secret://' || substr(secret_ref, 10)
        WHERE custody_mode = 'private_runner'
          AND secret_ref LIKE 'runner://%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE connector_credentials
        SET secret_ref = 'runner://' || substr(secret_ref, 26)
        WHERE custody_mode = 'private_runner'
          AND secret_ref LIKE 'customer-runner-secret://%'
        """
    )
