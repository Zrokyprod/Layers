# Silent Failure Demo

Five-minute story: an agent says a refund was processed, Stripe says it was not, Zroky catches the gap, then the private runner fixes it and proof closes the incident.

## Env

```powershell
$env:ZROKY_API_BASE="https://api.zroky.com"
$env:ZROKY_DASHBOARD_URL="https://app.zroky.com"
$env:ZROKY_PROJECT="<demo-project-id>"
$env:ZROKY_API_KEY="<project-api-key>"
$env:ZROKY_ADMIN_BEARER_TOKEN="<admin-or-owner-session-jwt>"
$env:STRIPE_SECRET_KEY="sk_test_..."
$env:ZROKY_STRIPE_SECRET_REF="STRIPE_KEY_PROJ_DEMO"
```

For local backend only, set `ZROKY_USE_PROJECT_HEADER_CONTEXT=1` if local settings allow project header context. Production needs the admin bearer token for pack/config/recovery/sweep admin routes.
For production active pull, set the same Stripe key value in Railway under the env var named by `ZROKY_STRIPE_SECRET_REF`; Zroky stores only that env var name.

Use a clean demo project. The Evidence hero is project-wide, so old outcome graphs in the same project will still count.

## Run

```powershell
python demos/silent-failure-demo/run_demo.py
```

Use `--yes` to skip pauses. Use `--no-browser` if presenting from a separate browser profile.

## Presenter Script

Act 1, the lie:

"This support agent says it refunded INR 4,500. The app log says success. No exception. No timeout. This is exactly the silent failure class customers usually find first."

Act 2, the catch:

"Now Zroky checks Stripe, not the agent log. Stripe has no refund for this charge. The outcome graph is missing, an incident opens, and the Evidence page shows Caught: 1. Agent ne bola ho gaya. Stripe ne bola nahi hua. Zroky ne farak pakda, bina customer complaint ke."

The script waits for the automatically created graph and triggers only the normal due-recheck endpoint. It does not build a graph or push an observation itself.

Act 3, the fix:

"We compile the recovery plan. It includes only the missing refund effect. The private runner claims the job, resolves the Stripe key from local env, creates the real Stripe test-mode refund, and reports completion. Zroky still does not resolve the incident from the runner claim."

Close:

"Now proof runs again. Stripe returns the refund record. The graph becomes verified and the incident resolves itself. Incident humne band nahi kiya. Stripe ke record ne band kiya."

## What To Show

- Evidence page before recovery: Caught is 1, graph classification is missing.
- Drill-down: expected refund effect, no actual refund observation, graph digest.
- Runner terminal: claim, signed dispatch prefix, Stripe refund completion.
- Evidence page after recheck: Caught is 0 for this run, verified proof has the Stripe refund observation digest.
