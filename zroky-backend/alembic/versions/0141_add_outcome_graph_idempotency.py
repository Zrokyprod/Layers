"""add outcome graph idempotency

Revision ID: 0141_add_outcome_graph_idempotency
Revises: 0140_create_final_source_connectors
Create Date: 2026-08-02
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0141_add_outcome_graph_idempotency"
down_revision = "0140_create_final_source_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("final_outcome_graphs") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True))

    seen: set[tuple[str, str, str]] = set()
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, project_id, environment, intent_id, graph_json "
            "FROM final_outcome_graphs ORDER BY created_at, id"
        )
    ).mappings()
    for row in rows:
        try:
            graph = json.loads(row["graph_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        run_id = graph.get("run_id") if isinstance(graph, dict) else None
        if not isinstance(run_id, str) or not run_id or graph.get("reconstructed_from_outbox_job_id"):
            continue
        key = f"initial:{run_id}:{row['intent_id']}"
        scope = (row["project_id"], row["environment"], key)
        if scope in seen:
            continue
        seen.add(scope)
        connection.execute(
            sa.text("UPDATE final_outcome_graphs SET idempotency_key = :key WHERE id = :id"),
            {"key": key, "id": row["id"]},
        )

    with op.batch_alter_table("final_outcome_graphs") as batch_op:
        batch_op.create_unique_constraint(
            "ux_final_outcome_graphs_scope_idempotency",
            ["project_id", "environment", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("final_outcome_graphs") as batch_op:
        batch_op.drop_constraint("ux_final_outcome_graphs_scope_idempotency", type_="unique")
        batch_op.drop_column("idempotency_key")
