# Zroky Manual QA Agent

This folder runs a local Python agent against the real Zroky control plane. It does not touch Stripe, Slack, CRM, billing, production, or customer systems. Mock tools only generate payloads; Zroky receives the real protected-action intents.

## 1. Create dashboard state

In `app.zroky.com`:

1. Go to `Settings -> API Keys` and create/copy a project key.
2. Go to `Agents -> Setup`.
3. Create or reuse `Manual QA Agent`.

## 2. Configure local env

```powershell
cd "D:\Zroky AI\examples\manual-agent"
Copy-Item .env.example .env
notepad .env
```

Paste your values:

```env
ZROKY_API_KEY=zk_live_...
ZROKY_PROJECT=proj_...
ZROKY_INGEST_URL=https://api.zroky.com
ZROKY_AGENT_NAME=Manual QA Agent
ZROKY_ENVIRONMENT=development
```

If the dashboard gives `ZROKY_PROJECT_ID`, either paste that into `ZROKY_PROJECT` or leave both values in `.env`. `agent.py` maps `ZROKY_PROJECT_ID` to `ZROKY_PROJECT` automatically.

## 3. Install

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install zroky python-dotenv
```

For local SDK development instead of the published package:

```powershell
pip install -e "..\..\zroky-sdk" python-dotenv
```

## 4. Smoke checks

```powershell
zroky doctor
zroky health
zroky ingest --test
```

Then refresh `app.zroky.com/home`. The first smoke event should unlock the first-run dashboard path if the backend accepts it.

## 5. Run scenarios one by one

First register the Manual QA action contracts:

```powershell
python agent.py bootstrap
```

If this returns `401` or `403`, your runtime key can send protected actions but cannot register action contracts. Use an admin session/key to install the contracts once, then return to the runtime key for scenario runs.

Then run scenarios:

```powershell
python agent.py access-grant
python agent.py refund-high
python agent.py crm-update
python agent.py deploy-change
python agent.py sequence-risk
python agent.py verifier-fail
python agent.py connector-missing
```

Or run everything:

```powershell
python agent.py all
```

## 6. What to verify in the dashboard

| Scenario | Modules to check | Expected product signal |
| --- | --- | --- |
| `access-grant` | Actions, Outcomes, Evidence | Safe action captured and proof path visible |
| `refund-high` | Actions, Approvals, Outcomes, Evidence | High-risk money action should exercise approval/hold behavior |
| `crm-update` | Actions, Outcomes | Customer-state mutation captured |
| `deploy-change` | Actions, Approvals | Production change appears as high-risk |
| `sequence-risk` | Actions, Policies, Approvals | Multiple normal actions form a risky sequence |
| `verifier-fail` | Actions, Outcomes | Source-of-record mismatch/failure path visible |
| `connector-missing` | Actions, Connectors | Missing verifier/connector gap visible |

## Notes

- The current Python SDK `zroky.protect()` submits protected-action intents. It does not accept `run=lambda` yet.
- Protected actions require an action contract. Run `python agent.py bootstrap` once before the first scenario.
- Keep `.env` local. It is ignored by git.
- Revoke the API key in `Settings -> API Keys` after destructive testing, then confirm the agent fails cleanly.
