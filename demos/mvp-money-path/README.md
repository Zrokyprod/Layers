# Zroky MVP Money Path Demo

This demo seeds a deterministic refund-support failure loop into a local Zroky database. It does not call real LLM providers, does not need provider keys, and does not add any production runtime path.

## What It Shows

1. A refund support agent receives: `Where is my refund?`
2. The bad agent version silently fails by returning generic refund policy text and never calling `get_refund_status`.
3. Zroky captures the call.
4. Diagnosis records `TOOL_NOT_CALLED`.
5. The public Issue groups the failure.
6. A deterministic mocked-tool replay with the fixed prompt/model/tool behavior passes.
7. The verified replay is represented as an active Golden with explicit expected behavior.
8. Regression CI blocks a PR that breaks the flow again.

## Seeded Demo Account

- Email: `demo@zroky.local`
- Password: `ZrokyDemo123!`
- Project: `demo-refund-money-path`
- Plan: Pro-level local entitlements, seeded through the existing subscription/entitlement tables.

## Run Locally

From the repo root:

```powershell
cd zroky-backend
$env:DATABASE_URL = "sqlite:///./.data/zroky-demo.db"
$env:AUTH_JWT_SECRET = "local-demo-secret"
$env:ALLOW_PROJECT_HEADER_CONTEXT = "true"
alembic upgrade head
python scripts/seed_mvp_money_path_demo.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
cd zroky-dashboard
$env:ZROKY_API_BASE_URL = "http://127.0.0.1:8000"
npm install
npm run dev
```

Open `http://localhost:3000`, log in with the demo account, and use the seeded project.

## Walkthrough URLs

After the seed script runs, it prints these exact local routes:

- Failure Inbox: `http://localhost:3000/home`
- Issue Detail: `http://localhost:3000/issues/demo-issue-refund-tool-not-called`
- Replay Lab: `http://localhost:3000/replay/demo-replay-refund-fixed`
- Goldens: `http://localhost:3000/goldens`
- CI Gates: `http://localhost:3000/ci-gates`

## Expected Proof Points

- Failure Inbox shows a critical/open refund issue with failure code `TOOL_NOT_CALLED`.
- Issue Detail explains that the agent answered with refund policy text instead of calling `get_refund_status`.
- Replay Lab shows the original generic answer on the left, the fixed tool-grounded candidate answer on the right, and `verified_fix` in the verification panel.
- Goldens shows `Refund status protected flow` with an active trace. The failed output is stored as source evidence, while expected behavior is the fixed refund-status answer.
- CI Gates shows a failing Regression CI run for a demo PR. The run verdict is `fail`, regression rate is `100%`, and it blocks the PR because the broken version skipped `get_refund_status`.

## Resetting

The seed script is idempotent for the stable demo IDs in `refund_money_path_fixture.json`. Re-running it replaces only the demo rows for `demo-refund-money-path` and leaves unrelated local data untouched.
