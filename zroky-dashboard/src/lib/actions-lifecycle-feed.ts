import { getActionsLifecycleSummary, type ActionsLifecycleSummaryResponse } from "@/lib/api";
import {
  actionLifecycleCounts,
  buildActionLifecycle,
  type ActionLifecycleCounts,
  type ActionLifecycleRow,
} from "@/lib/action-lifecycle";

export type ActionsLifecycleFeed = {
  summary: ActionsLifecycleSummaryResponse;
  rows: ActionLifecycleRow[];
  counts: ActionLifecycleCounts;
};

export async function loadActionsLifecycleFeed(
  params: { days?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ActionsLifecycleFeed> {
  const summary = await getActionsLifecycleSummary(params, signal);
  const rows = buildActionLifecycle({
    intents: summary.data.intents,
    decisions: summary.data.approvals,
    outcomes: summary.data.outcomes,
    attempts: summary.data.attempts ?? summary.data.stale_attempts,
    staleAttemptIds: summary.data.stale_attempts.map((attempt) => attempt.attempt_id),
    mutations: summary.data.mutations,
  });
  return {
    summary,
    rows,
    counts: actionLifecycleCounts(rows),
  };
}
