# Bugfix Requirements Document

## Introduction

The replay worker is the gate that decides whether a candidate prompt fix is safe to ship. Today that gate is broken: the worker reports `status="pass"` for candidate fixes that introduce real regressions because no real LLM call is ever made. Any prompt edit — including one that genuinely degrades output quality — slips through with a low `diff_metric` and a green check, and the control plane then approves the candidate fix PR. This is a Very High severity defect: the platform is silently shipping regressions while reporting that it caught them.

The defect lives in two collaborating steps of the replay execution path:

- The call-execution step never reaches the configured LLM provider; it runs a fixed inline Python script and treats that script's printout as the model output.
- The diff metric is computed as a character-set Jaccard distance between the golden `expected_output` and the stub's printout, which is independent of the patched prompt and therefore independent of whether the candidate fix is good or bad.

The README and the technical plan §8 both specify the intended behavior: a real provider call dispatched via `httpx`, with embedding-cosine diff against the golden output, executed under existing zero-trust guarantees (HMAC artifact verification, sandboxed subprocess, hard timeout, pull-only network model, no secret leakage). This document specifies the observable behavior change required to make the gate honest, and the preservation invariants that must continue to hold.

The bug condition `C(X)` over a replay job `X` (a `ReplayJob` whose `candidate_fix_diff` is applied to the captured call context) is: the candidate fix produces a meaningfully different output from the golden `expected_output` when run against the configured provider/model. After the fix, jobs satisfying `C(X)` must yield `status="fail"` (or `status="error"` if execution itself fails); jobs satisfying `¬C(X)` must yield `status="pass"`; jobs with invalid signatures or malformed artifacts must yield `status="error"` without ever issuing a provider call.

## Bug Analysis

### Current Behavior (Defect)

Behavior observed today when a replay job is executed.

1.1 WHEN a replay job is executed against any provider/model THEN the system runs a fixed inline Python stub via `python3 -c` instead of calling the LLM provider, so the patched prompt is never sent to a model.

1.2 WHEN the system computes `diff_metric` THEN it compares `expected_output` against the stub's printout using character-set Jaccard distance, producing a value that does not reflect any semantic difference between the candidate fix's actual output and the golden output.

1.3 WHEN a `candidate_fix_diff` introduces a behavior regression in the patched prompt THEN the system returns `ReplayResult(status="pass", diff_metric ≤ 0.3)` because the stub stdout is a constant JSON shape independent of prompt content, so the regression is reported as a passing fix.

1.4 WHEN a `candidate_fix_diff` is benign and does not change behavior THEN the system also returns `status="pass"` for the same stub-based reason, so `"pass"` and `"fail"` are not actually distinguishable and the replay signal is meaningless.

1.5 WHEN the captured artifact specifies a `provider` field (e.g. `openai`, `anthropic`, `google`) and a `model` field THEN the system ignores those fields for execution and emits only `{"replay": true, "prompt_len": ..., "model": ...}` as the supposed model output.

1.6 WHEN a malformed or adversarial artifact is processed THEN the system has no per-job token or cost cap enforced during execution, leaving the worker exposed to unbounded provider spend as soon as a real provider call is wired in.

1.7 WHEN execution fails for any reason other than `subprocess.TimeoutExpired` THEN the system can still return `status="pass"` because pass/fail is gated on a meaningless `diff_metric` rather than on whether the provider call actually succeeded.

### Expected Behavior (Correct)

Behavior the system SHALL exhibit after the fix, paired one-to-one with the defects above.

2.1 WHEN a replay job is executed against a supported provider (`openai`, `anthropic`, `google`) THEN the system SHALL dispatch a real provider HTTP call via `httpx` carrying the patched prompt together with the artifact's model and call parameters, using the customer's vaulted provider key, and SHALL capture `(output_text, tokens, cost, latency)` from the response.

2.2 WHEN the system computes `diff_metric` THEN it SHALL produce a value in `[0.0, 1.0]` that reflects the semantic distance between the captured `output_text` and `expected_output`, using embedding cosine distance as the primary metric and a deterministic textual distance only as a documented fallback when embeddings are unavailable.

2.3 WHEN a `candidate_fix_diff` introduces a behavior regression in the patched prompt THEN the system SHALL return `status="fail"` with a `diff_metric` that exceeds the configured pass threshold, so the control plane does not approve the candidate fix PR.

2.4 WHEN a `candidate_fix_diff` is benign and the patched-prompt output is semantically equivalent to `expected_output` THEN the system SHALL return `status="pass"` with a `diff_metric` at or below the pass threshold.

2.5 WHEN the artifact specifies a `provider` and `model` THEN the system SHALL route the call to that provider's chat/completions endpoint and SHALL faithfully include the model identifier and call parameters from the artifact in the request.

2.6 WHEN a per-job token cap or cost cap is exceeded during execution THEN the system SHALL terminate the provider call, SHALL return `status="error"` with an `error_message` indicating the cap (e.g. `"token budget exceeded"`), and SHALL NOT proceed to scoring.

2.7 WHEN the provider call fails (network error, provider non-2xx, parse error) or any other execution step fails outside of the timeout path THEN the system SHALL return `status="error"` with a non-revealing `error_message` rather than `status="pass"`.

2.8 WHEN the artifact's HMAC signature is missing or invalid, or when the artifact is malformed/unparseable THEN the system SHALL return `status="error"` and SHALL NOT issue any provider call, download additional resources, or apply the diff.

2.9 WHEN the system writes to logs, `error_message`, `stdout_tail`, or any other field of `ReplayResult` THEN it SHALL NOT include the customer's provider API key, the `ARTIFACT_SIGNING_KEY`, the `WORKER_TOKEN`, or any other secret material.

### Unchanged Behavior (Regression Prevention)

Behavior that exists today and SHALL continue to hold after the fix.

3.1 WHEN an artifact arrives with an invalid HMAC signature THEN the system SHALL CONTINUE TO reject the job before any download or execution and return `status="error"` with `error_message="Artifact signature verification failed"`.

3.2 WHEN a job's wall-clock execution exceeds `JOB_TIMEOUT_SECONDS` THEN the system SHALL CONTINUE TO hard-kill the execution and return `status="error"` with the existing timeout message.

3.3 WHEN the worker is deployed in a customer VPC THEN the system SHALL CONTINUE TO operate in pull-only mode against `CONTROL_PLANE_URL` with no inbound ports opened and no listening sockets beyond the existing `/health` and `/ready` endpoints.

3.4 WHEN the control plane and dashboard consume worker output THEN the system SHALL CONTINUE TO emit results matching the existing `ReplayJob` / `ReplayResult` Pydantic protocol; any new fields SHALL be additive and optional so existing consumers parse responses without modification.

3.5 WHEN `/health` is queried THEN the system SHALL CONTINUE TO return `{"status": "ok"}` with HTTP 200.

3.6 WHEN `/ready` is queried with `WORKER_TOKEN` configured THEN the system SHALL CONTINUE TO return HTTP 200 indicating readiness; with `WORKER_TOKEN` unset it SHALL CONTINUE TO return HTTP 503.

3.7 WHEN the worker boots without `WORKER_TOKEN` configured THEN the system SHALL CONTINUE TO log a dev-mode warning and SHALL NOT start the poll loop.

3.8 WHEN a replay job is executed THEN the system SHALL CONTINUE TO sandbox execution inside a subprocess (or equivalent isolation boundary) so a misbehaving job cannot crash the poll loop or contaminate other in-flight jobs.

3.9 WHEN multiple jobs are dispatched concurrently THEN the system SHALL CONTINUE TO honor `MAX_CONCURRENT_JOBS` as the ceiling for parallel execution.

3.10 WHEN the worker reports a result THEN the system SHALL CONTINUE TO POST to `/v1/replay/result` with the existing payload shape `{worker_token, result}` and the existing `Authorization: Bearer <WORKER_TOKEN>` header.

3.11 WHEN the worker polls for jobs THEN the system SHALL CONTINUE TO POST to `/v1/replay/poll` with `{worker_token, capacity}` and SHALL CONTINUE TO treat HTTP 204 as "no jobs available".

3.12 WHEN a replay job's `candidate_fix_diff` is empty or whitespace-only THEN the system SHALL CONTINUE TO execute the job against the unmodified prompt rather than rejecting it.
