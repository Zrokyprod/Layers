"""Serializers for outcome route responses."""

from app.schemas.outcomes import (
    ClusterView,
    OutcomeReconciliationView,
    OutcomeTypeView,
    OutcomeView,
    SourceMutationView,
    SummaryResponse,
)
from app.services.outcome_attribution import OutcomeSummary
from app.services.outcome_reconciliation import reconciliation_to_dict
from app.services.source_mutations import source_mutation_to_dict


def _serialize_outcome(o) -> OutcomeView:
    return OutcomeView(
        id=o.id,
        project_id=o.project_id,
        call_id=o.call_id,
        outcome_type=o.outcome_type,
        amount_usd=float(o.amount_usd),
        source=o.source,
        occurred_at=o.occurred_at,
        external_ref=o.external_ref,
        created_at=o.created_at,
    )


def _serialize_summary(s: OutcomeSummary) -> SummaryResponse:
    return SummaryResponse(
        window_days=s.window_days,
        total_outcome_usd=s.total_outcome_usd,
        linked_outcome_count=s.linked_outcome_count,
        unlinked_outcome_count=s.unlinked_outcome_count,
        avg_cost_per_linked=s.avg_cost_per_linked,
        by_type=[
            OutcomeTypeView(
                outcome_type=t.outcome_type,
                total_usd=t.total_usd,
                count=t.count,
                avg_usd=t.avg_usd,
            )
            for t in s.by_type
        ],
        by_cluster=[
            ClusterView(
                agent_name=c.agent_name,
                detector=c.detector,
                outcome_cost_usd=c.outcome_cost_usd,
                outcome_count=c.outcome_count,
                failure_count=c.failure_count,
                estimated_monthly_savings_usd=c.estimated_monthly_savings_usd,
                top_outcome_type=c.top_outcome_type,
            )
            for c in s.by_cluster
        ],
    )


def _serialize_reconciliation(row) -> OutcomeReconciliationView:
    return OutcomeReconciliationView(**reconciliation_to_dict(row))


def _serialize_source_mutation(row) -> SourceMutationView:
    return SourceMutationView(**source_mutation_to_dict(row))


