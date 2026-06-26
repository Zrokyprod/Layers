# Zroky Customer-Hosted Protected Runner

This runner executes approved protected actions without returning protected credentials to the agent or Zroky control plane.

## Run locally

```bash
export ZROKY_INGEST_URL=https://api.zroky.com
export ZROKY_API_KEY=zk_live_replace_me
export ZROKY_PROJECT=proj_replace_me
export ZROKY_RUNNER_ID=runner_replace_me
export ZROKY_RUNNER_INSTANCE_ID=customer-prod-runner-1
export ZROKY_RUNNER_SECRET_PAYMENTS_STRIPE='{"secret_key":"sk_live_replace_me"}'

zroky runner daemon \
  --supported-operation-kind TRANSFER \
  --supported-operation-kind UPDATE \
  --supported-operation-kind SEND \
  --supported-operation-kind EXECUTE
```

## Run with Docker Compose

From `zroky-sdk`:

```bash
cp examples/env.runner.example examples/.env.runner
docker compose -f examples/docker-compose.runner.yml up --build
```

## Credential boundary

The control plane stores only a protected credential reference such as:

```text
customer-runner-secret://payments/stripe
```

The runner maps that reference to:

```text
ZROKY_RUNNER_SECRET_PAYMENTS_STRIPE
```

The secret value stays in the customer runtime. Runner result summaries are redacted before they are sent back to Zroky.

## Supported first-launch adapters

- `generic_rest`
- `stripe_refund`

The first launch catalog can mention `razorpay_refund`, `zendesk_ticket`, and `customer_message` only as planned/template adapters until customer adapter callbacks or native implementations are shipped.
