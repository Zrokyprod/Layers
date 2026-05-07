# zroky-sdk

Python SDK for ZROKY production AI diagnosis.

## Install

### Local install (current path)

```bash
pip install -e ./zroky-sdk
```

### Local install with LangChain integration

```bash
pip install -e "./zroky-sdk[langchain]"
```

### Package publish status

The SDK is currently consumed via local install in this repository.
No public PyPI release is published yet.

## Dependency policy

- Core dependency surface stays minimal: `httpx>=0.27.0`.
- `bcrypt` is not a runtime dependency of the SDK because SDK code does not perform password hashing.
- LangChain integration is optional and installed via the `langchain` extra.

## Release and publish

GitHub Actions workflow for SDK publish:

- [.github/workflows/zroky-sdk-publish.yml](../.github/workflows/zroky-sdk-publish.yml)

### Required GitHub repository secrets

- `TEST_PYPI_API_TOKEN`
- `PYPI_API_TOKEN`

### Manual publish (recommended for first release)

1. Bump `version` in [pyproject.toml](pyproject.toml).
2. Open GitHub Actions and run `Zroky SDK Publish`.
3. Choose `target_repository=testpypi` first.
4. Validate install from TestPyPI.
5. Re-run workflow with `target_repository=pypi`.

### Tag-driven publish to PyPI

Push a tag in this format after version bump:

```bash
git tag zroky-sdk-v0.1.0
git push origin zroky-sdk-v0.1.0
```

The workflow enforces that tag version matches [pyproject.toml](pyproject.toml).

## Preflight validation

The SDK supports advisory pre-execution validation before provider calls.

- It never mutates your payload.
- It does not block provider execution unless blocking warning types are configured.
- It prints only when warnings exist.
- It includes warning-spam suppression.

### Enable

Use environment variables:

```bash
export ZROKY_VALIDATE_PREFLIGHT=true
export ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE=1.0
```

Or configure in code:

```python
import zroky

zroky.init(
    validate_preflight=True,
    validate_preflight_sample_rate=1.0,
)
```

### Rollout control

`ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE` must be between `0.0` and `1.0`.

- `0.0` means preflight is effectively disabled.
- `1.0` means all eligible calls are checked.
- Values in between run deterministic sampling.

Sampling uses a stable hash of `provider|model|prompt_fingerprint`.
This keeps behavior predictable and avoids random flip-flops on repeated call shapes.

### Recommended rollout profile

- Development: `1.0`
- Staging: `0.5`
- Production initial: `0.1`
- Production ramp: `0.25 -> 0.5 -> 1.0` after monitoring

### Public validation API

```python
result = zroky.validate(payload)
zroky.print_validation(result)
```

Return shape:

```json
{
  "valid": false,
  "warnings": [
    {
      "type": "TOKEN_OVERFLOW",
      "confidence": 0.92,
      "message": "Estimated prompt size is near model limit.",
      "suggested_fix": "Truncate input and summarize history."
    }
  ]
}
```

### Warning types

- `TOKEN_OVERFLOW`
- `RATE_LIMIT_RISK`
- `AUTH_RISK`

## Production Prevention

For wrapped calls through `zroky.call()` / `zroky.acall()`, the SDK can apply
the same protection policy on every request instead of requiring each call site
to remember retry/fallback settings.

```python
zroky.init(
    retry_max_retries=2,
    fallback_models=["gpt-4o-mini", "claude-3-haiku"],
    fallback_adaptive=True,
    rate_limits={
        "openai/gpt-4o": {"rpm": 500, "tpm": 30000},
    },
    preflight_blocking_warning_types=["AUTH_RISK"],
)
```

Environment equivalents:

```bash
export ZROKY_FALLBACK_MODELS=gpt-4o-mini,claude-3-haiku
export ZROKY_FALLBACK_ADAPTIVE=true
export ZROKY_PREFLIGHT_BLOCKING_WARNINGS=AUTH_RISK
```

Behavior:

- Retry handles transient rate-limit, timeout, network, and 5xx provider errors.
- Fallback is applied globally when `fallback_models` is configured, with
  per-call `fallback=[...]` still allowed as an override.
- Circuit breaker skips models with repeated recent failures when a fallback is
  available.
- Auth preflight can block before the provider call and records a `blocked`
  telemetry event, so dashboard evidence still exists.
