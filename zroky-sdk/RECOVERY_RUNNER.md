# Recovery runner deployment

The recovery runner belongs in the customer's environment. Recovery credentials are resolved from that environment and are never returned by the Zroky API.

## Railway

Create a worker service from this repository with:

- Root directory: `/zroky-sdk`
- Config file path: `/zroky-sdk/railway.toml`
- No public domain or HTTP health check

Set these service variables:

```text
ZROKY_API_KEY=<project API key>
ZROKY_PROJECT=<project id>
ZROKY_EXECUTOR_REF=customer-recovery-executor://your-team/recovery
ZROKY_POLL_SECONDS=30
```

For every `credential_ref` used by a recovery playbook, set the corresponding local runner variable. The name is `ZROKY_RUNNER_SECRET_` plus the normalized credential path. For example:

```text
credential_ref: customer-runner-secret://payments/stripe
variable name:  ZROKY_RUNNER_SECRET_PAYMENTS_STRIPE
variable value: {"secret_key":"<restricted Stripe key>"}
```

Use the least-privileged provider credential that can execute the playbook. Do not put provider credentials in assurance packs, connector records, or Zroky API requests.

`ZROKY_API_URL` is optional and defaults to `https://api.zroky.com`. The container starts `python -m zroky.recovery_runner`, polls for work, heartbeats active leases, and reports completion for proof-driven re-verification.
