from __future__ import annotations

import argparse
import json
import os
import webbrowser

from _common import (
    EXECUTOR_REF,
    PLAYBOOK_KEY,
    RUNNER_CREDENTIAL_REF,
    SOURCE_BINDING,
    ApiClient,
    DemoConfig,
    evidence_url,
    latest_refund_for_charge,
    now_iso,
    refund_observation_state,
    refunds_for_charge,
    save_state,
    presenter_pause,
)
from lying_agent import declare_lie
from seed import setup
from zroky._runner import credential_env_name
from zroky.recovery_runner import RecoveryRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Zroky silent failure demo.")
    parser.add_argument("--yes", action="store_true", help="Do not pause between acts.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the evidence page.")
    args = parser.parse_args()

    config = DemoConfig.from_env()
    api = ApiClient(config)

    presenter_pause(
        "Setup: create a fresh Stripe test charge, configure the Stripe connector, "
        "and seed refund_flow_v1.",
        auto=args.yes,
    )
    state = setup()

    presenter_pause(
        "Act 1: the support agent will declare a refund and claim success, "
        "but it will not call Stripe.",
        auto=args.yes,
    )
    state = declare_lie()

    presenter_pause(
        "Act 2: Zroky checks Stripe as the system of record. There is no refund.",
        auto=args.yes,
    )
    refunds = refunds_for_charge(config, state["charge_id"])
    if refunds:
        raise RuntimeError(f"Expected no refund before recovery, found {refunds[0]['id']}.")
    print("Stripe says: no refund exists for the charge.")

    graph = api.request("POST", f"/v1/runs/{state['run_id']}/outcome-graph", body={})
    incidents = api.request("GET", "/v1/incidents")
    incident = next(item for item in incidents if item["outcome_graph_id"] == graph["id"])
    summary = api.request("GET", "/v1/outcome-graphs/coverage-summary")
    state.update({"graph_id": graph["id"], "incident_id": incident["id"]})
    save_state(state)

    caught = sum(summary["counts"].get(key, 0) for key in ("wrong", "missing", "forbidden", "duplicate"))
    print(f"Outcome graph classification: {graph['classification']}")
    print(f"Incident opened: {incident['id']} status={incident['status']}")
    print(f"Evidence page hero should show Caught: {caught}")
    print(f"Graph digest: {graph['graph_digest']}")
    if not args.no_browser:
        webbrowser.open(evidence_url(config, graph["id"]))

    presenter_pause(
        "Act 3: compile the recovery plan, execute it with the private runner, "
        "then trigger proof recheck.",
        auto=args.yes,
    )
    compiled = api.request(
        "POST",
        "/v1/recovery/compile-plan",
        body={"incident_id": incident["id"], "playbook_key": PLAYBOOK_KEY},
    )
    plan = compiled["plan"]
    for step in plan["steps"]:
        step.setdefault("target", {})["charge"] = state["charge_id"]
    print("Compiled recovery plan:")
    print(json.dumps(plan["steps"], indent=2))

    execution = api.request(
        "POST",
        f"/v1/incidents/{incident['id']}/execute-recovery",
        admin=True,
        idempotency_key=f"{state['demo_id']}:execute-recovery",
        body={"executor_ref": EXECUTOR_REF, "plan": plan},
    )
    print(f"Recovery queued: outbox_job_id={execution['outbox_job_id']}")

    os.environ[credential_env_name(RUNNER_CREDENTIAL_REF)] = json.dumps(
        {"secret_key": config.stripe_secret_key}
    )
    runner = RecoveryRunner(
        executor_ref=EXECUTOR_REF,
        api_key=config.api_key,
        project=config.project,
        api_base=config.api_base,
        lease_seconds=90,
    )
    dispatch = runner.claim_once()
    if dispatch is None:
        raise RuntimeError("Runner did not claim a recovery dispatch.")
    print(f"runner: claimed {dispatch['outbox_job_id']} token={dispatch['fencing_token']}")
    print(f"runner: signed dispatch signature={dispatch['signature'][:16]}...")
    runner.heartbeat(dispatch)
    overall, step_results = runner._execute_dispatch(dispatch)  # demo script: expose live step output
    completed = runner.complete(dispatch, overall=overall, step_results=step_results)
    print(f"runner: complete overall={overall} job_status={completed['job_status']}")
    if overall != "succeeded":
        raise RuntimeError(f"Recovery runner did not succeed: {step_results}")

    refund = latest_refund_for_charge(config, state["charge_id"])
    observed_state = refund_observation_state(refund)
    observation = api.request(
        "POST",
        "/v1/observations",
        body={
            "environment": "production",
            "run_id": state["run_id"],
            "intent_id": state["intent_id"],
            "source_kind": "stripe_refund",
            "observed_object_ref": f"stripe:refund:{refund['id']}",
            "observed_state": observed_state,
            "provenance": {
                "source_binding": SOURCE_BINDING,
                "stripe_object": "refund",
                "mode": "test",
            },
            "observed_at": now_iso(),
            "read_at": now_iso(),
        },
    )
    print(f"Stripe refund observed: {refund['id']}")
    print(f"Observation digest: {observation['observation_digest']}")

    sweep = api.request("POST", "/v1/outcome-graphs/recheck-due", admin=True)
    print(f"Proof recheck: checked={sweep['checked']} updated={sweep['updated']}")

    final_incident = api.request("GET", f"/v1/incidents/{incident['id']}")
    final_summary = api.request("GET", "/v1/outcome-graphs/coverage-summary")
    print(f"Incident final status: {final_incident['status']}")
    print(f"Coverage: {final_summary['coverage_percent']}% verified")
    print("Closing line: Incident humne band nahi kiya. Stripe ke record ne band kiya.")


if __name__ == "__main__":
    main()
