"""create outcome_events table — Cost-of-Failure Attribution.

Revision ID: 0066_create_outcome_events
Revises: 0065_create_judge_calibration_tables
Create Date: 2026-05-19 00:00:00.000000

Schema notes (Cost-of-Failure Attribution — CFO Wedge):

  outcome_events:
      One row per business-outcome event mapped to a Zroky call.
      Customers emit these via three paths:

        1. SDK:    zroky.outcome(call_id=..., type="refund_issued", amount_usd=49)
        2. Direct: POST /v1/outcomes
        3. Webhook receivers: /v1/outcomes/webhooks/{zendesk|salesforce}
           These normalise provider-specific payloads into a canonical row.

      call_id is nullable because some outcomes arrive post-facto or are
      linked by the customer's own correlation key (external_ref) before the
      SDK call_id is known.  Attribution queries LEFT JOIN to calls and
      diagnosis_jobs on call_id; unlinked rows surface in the "unattributed"
      bucket.

      Idempotency:
        UNIQUE(project_id, idempotency_key) WHERE idempotency_key IS NOT NULL
        Webhook re-delivers never double-count.
        SDK retries pass idempotency_key=call_id+":"+outcome_type.

      Attribution join (all in application code, no materialised views):
        outcome_events.call_id
          → calls.agent_name / calls.model
          → diagnosis_jobs.agent_name / diagnosis_jobs.payload_json (detector)

      Replay savings (pre-deploy $ tag):
        replay_run_traces(status='pass') → golden_traces.call_id
          → outcome_events.amount_usd SUM

      Indexes:
        (project_id, occurred_at DESC) — primary dashboard query
        (call_id) WHERE call_id IS NOT NULL — attribution join
        UNIQUE (project_id, idempotency_key) — dedup
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0066_create_outcome_events"
down_revision = "0065_create_judge_calibration_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_events",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
            comment="UUID primary key.",
        ),
        sa.Column(
            "project_id",
            sa.String(length=64),
            nullable=False,
            comment="Tenant project_id — RLS scope.",
        ),
        sa.Column(
            "call_id",
            sa.String(length=64),
            nullable=True,
            comment="FK to calls.id. NULL when outcome is not yet linked to a specific call.",
        ),
        sa.Column(
            "outcome_type",
            sa.String(length=64),
            nullable=False,
            comment=(
                "Business event type: refund_issued | ticket_escalated | "
                "human_handoff | churn | compliance_fine | retry_cost | custom"
            ),
        ),
        sa.Column(
            "amount_usd",
            sa.Numeric(precision=14, scale=4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Monetary cost of this outcome in USD.",
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'USD'"),
            comment="ISO 4217 three-letter code of the original currency (informational).",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'api'"),
            comment="Ingest path: sdk | api | zendesk | salesforce | csv.",
        ),
        sa.Column(
            "external_ref",
            sa.String(length=255),
            nullable=True,
            comment="Provider-native ID (Zendesk ticket ID, Salesforce opportunity ID, …).",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
            comment="Dedup key: UNIQUE per project. SDKs set this; webhook receivers derive from external_ref.",
        ),
        sa.Column(
            "metadata_json",
            sa.Text(),
            nullable=True,
            comment="Arbitrary caller-supplied context (customer_id, order_id, …).",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the business event happened (may predate ingest).",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Ingest timestamp.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount_usd >= 0",
            name="ck_outcome_events_amount_positive",
        ),
        sa.CheckConstraint(
            "source IN ('sdk','api','zendesk','salesforce','csv')",
            name="ck_outcome_events_source",
        ),
    )

    # Primary dashboard query: project slice ordered by recency
    op.create_index(
        "ix_outcome_events_project_occurred",
        "outcome_events",
        ["project_id", "occurred_at"],
        postgresql_ops={"occurred_at": "DESC"},
    )

    # Attribution join: outcome → call → agent/anomaly
    op.create_index(
        "ix_outcome_events_call_id",
        "outcome_events",
        ["call_id"],
        postgresql_where=sa.text("call_id IS NOT NULL"),
    )

    # Webhook / SDK dedup
    op.create_index(
        "ix_outcome_events_idempotency",
        "outcome_events",
        ["project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outcome_events_idempotency", table_name="outcome_events"
    )
    op.drop_index(
        "ix_outcome_events_call_id", table_name="outcome_events"
    )
    op.drop_index(
        "ix_outcome_events_project_occurred", table_name="outcome_events"
    )
    op.drop_table("outcome_events")
