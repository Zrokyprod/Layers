# Zroky Design-Partner Install Kit

This kit gives a design partner one runnable proof that Zroky can protect an
autonomous agent action end to end:

1. Capture a high-stakes refund action from an agent trace.
2. Stop the unsafe action at runtime with a policy decision.
3. Reconcile the agent's claimed refund against a ledger system of record.
4. Export a redacted evidence pack with a stable evidence hash.

The kit is intentionally narrow. It proves the paid-launch loop for one
money-touching action before expanding to CRM, DevOps, access, or procurement
connectors.

## What The Partner Should Believe

A successful run means:

- Zroky saw the action before it committed.
- Zroky blocked or held the risky action instead of silently allowing it.
- Zroky checked the real ledger outcome, not just the agent's text output.
- Zroky produced an audit-ready evidence hash.
- No API key or ledger token was printed into the handoff artifacts.

It does not mean the whole deployment is production-ready. Live launch still
requires production secrets, billing/webhook smoke, worker readiness, and
gateway recovery proof.

## Local Proof

Run this first before touching partner systems:

```powershell
python scripts/run_design_partner_install_kit.py --json --write-summary artifacts/design-partner-summary.json --write-evidence artifacts/design-partner-evidence.json
```

Expected summary:

- `mode`: `local_demo`
- `runtime_policy.allowed`: `false`
- `outcome_reconciliation.verdict`: `matched`
- `evidence_pack.verification_status`: `pass`
- `proof.secrets_redacted`: `true`
- `evidence_pack.evidence_hash`: 64 hex characters

Artifacts:

- `artifacts/design-partner-summary.json`: redacted customer-facing proof summary.
- `artifacts/design-partner-evidence.json`: redacted raw evidence pack for audit.

## Live Partner Smoke

Use this after the partner has a Zroky project, API credential, and a ledger API
record that can be safely queried:

```powershell
python scripts/run_design_partner_install_kit.py --api-base-url https://api.zroky.ai --api-key <zroky_api_key> --ledger-base-url https://ledger.example.com/api --ledger-bearer-token <ledger_token> --refund-id <refund_id> --json --write-summary artifacts/design-partner-live-summary.json --write-evidence artifacts/design-partner-live-evidence.json
```

Use `--bearer-token` instead of `--api-key` when the partner authenticates with
a user/session bearer token. Use `--project-id` when the API key is not already
bound to a single project.

## Required Inputs

| Input | Required for local | Required for live | Notes |
| --- | --- | --- | --- |
| `--api-base-url` | No | Yes | Zroky API base URL. Omit for local demo. |
| `--api-key` or `--bearer-token` | No | Yes | Zroky auth. Never paste into screenshots. |
| `--ledger-base-url` | No | Yes | HTTPS ledger API base URL. |
| `--ledger-bearer-token` | No | Yes | Ledger auth token. Redacted from artifacts. |
| `--refund-id` | No | Yes | Existing refund id to verify in the ledger. |
| `--amount-usd` | No | Optional | Use when the partner refund amount differs from the fixture. |
| `--currency` | No | Optional | Defaults to the fixture currency. |
| `--status` | No | Optional | Defaults to the fixture status. |

## Pass Criteria

The handoff is a pass only when all of these are true:

- `captured_call_linked`
- `unsafe_action_stopped`
- `matched_outcome_shown`
- `evidence_hash_visible`
- `evidence_pack_passed`
- `secrets_redacted`

Any false value blocks the pilot handoff. Do not call a run verified when the
status is `not_verified`, the outcome is `mismatched`, or the evidence hash is
missing.

## Failure Meanings

| Failure | Meaning | First fix |
| --- | --- | --- |
| `unsafe_action_stopped=false` | Runtime policy did not block/hold the risky action. | Check mandate, action type, impact amount, and policy thresholds. |
| `matched_outcome_shown=false` | System of record did not match the agent's claim. | Compare refund id, amount, currency, and status. |
| `evidence_pack_passed=false` | Evidence exists but is not verified. | Open the evidence pack and inspect decision/outcome status. |
| `secrets_redacted=false` | A secret leaked into summary or evidence. | Stop the handoff, rotate the leaked token, and fix redaction before rerun. |
| HTTP 401/403 | Zroky or ledger auth failed. | Check API key, bearer token, project id, and ledger scopes. |
| HTTP 404 from ledger | Refund id was not found in the system of record. | Use a valid refund id or adjust the ledger path template. |

## Buyer Demo Script

1. Show the agent attempting a refund-like high-stakes action.
2. Run the install kit and point to `runtime_policy.allowed=false`.
3. Show `outcome_reconciliation.verdict=matched`.
4. Show the 64-character `evidence_hash`.
5. Open the evidence JSON and show decision, policy snapshot, reconciliation,
   audit entries, and hash. Do not show raw secrets.
6. Explain the next live step: connect the partner's real ledger/refund API and
   repeat the same proof against their system of record.

## Expansion After Refund

After this refund proof passes with a real partner, add the next connector only
when it has a committed design partner:

- CRM/customer-record connector
- DevOps/deploy connector
- IT/access connector
- Procurement/expense connector
- Email/ticketing connector
