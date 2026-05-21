.PHONY: install dev replay-smoke docker-build docker-run

install:
	pip install -e .

dev:
	uvicorn app.main:app --reload --port 8080

replay-smoke:
	@echo "Running replay smoke test against local worker..."
	python - <<'EOF'
import json, gzip, hmac, hashlib, httpx, os, sys

base = os.getenv("REPLAY_WORKER_URL", "http://localhost:8080")

r = httpx.get(f"{base}/health")
assert r.status_code == 200, f"Health check failed: {r.status_code}"
print("OK /health")

artifact = gzip.compress(json.dumps({
    "prompt": "What is 2 + 2?",
    "model": "gpt-4o-mini",
    "expected_output": '{"answer": 4}',
}).encode())

signing_key = os.getenv("ARTIFACT_SIGNING_KEY", "")
sig = hmac.new(signing_key.encode(), b"smoke://artifact", hashlib.sha256).hexdigest() if signing_key else "dev"

from app.models import ReplayJob
from app.runner import run_job
from datetime import datetime, timezone

job = ReplayJob(
    replay_id="smoke-001",
    trace_id="trace-smoke",
    fix_pr_id="pr-smoke",
    candidate_fix_diff="",
    artifact_url="smoke://artifact",
    artifact_signature=sig,
    created_at=datetime.now(timezone.utc),
)

from app.config import get_settings
settings = get_settings()
result = run_job(job, signing_key=settings.ARTIFACT_SIGNING_KEY)
assert result.replay_id == "smoke-001"
print(f"OK replay smoke: status={result.status} diff_metric={result.diff_metric}")
EOF

docker-build:
	docker build -t zroky-replay-worker:local .

docker-run:
	docker run --rm -p 8080:8080 \
		-e WORKER_TOKEN=$(WORKER_TOKEN) \
		-e CONTROL_PLANE_URL=$(CONTROL_PLANE_URL) \
		-e ARTIFACT_SIGNING_KEY=$(ARTIFACT_SIGNING_KEY) \
		zroky-replay-worker:local
