# Failure to Golden

This is the Zroky Watch OSS story developers should understand in one minute.

```text
Production agent failure
  ↓
SDK or Gateway captures one connected trace
  ↓
Zroky Pilot groups related traces into an Issue
  ↓
Replay Worker proves a candidate fix against the same incident
  ↓
Passing replay becomes a Golden
  ↓
CI blocks the regression before release
```

## Example incident

- Agent: `refund-agent`
- Workflow: `refund-review`
- Prompt version: `refund-v42`
- Failure path: retrieval timeout selected a stale policy chunk
- Impact: repeated tool loop, weak evidence, wasted tokens

## OSS responsibility

The OSS data plane captures and transports evidence:

- Python SDK
- JS/TS SDK
- Gateway
- Replay Worker

## Paid control-plane responsibility

Zroky Cloud/Pilot handles the private intelligence layer:

- Issue grouping
- Root-cause diagnosis
- Replay orchestration
- Judge verification
- Golden promotion
- CI gate enforcement
