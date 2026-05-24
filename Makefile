.PHONY: self-host self-host-seed self-host-down self-host-logs self-host-ps \
        self-host-rebuild capture-e2e-local capture-smoke-local lint-sizes api-contract-check schema-check help

ENV_FILE := zroky-backend/.env.self-host
ENV_EXAMPLE := zroky-backend/.env.self-host.example

# ── Self-host targets ────────────────────────────────────────────────────────

## self-host: copy env example if missing, run migrations, start all services
self-host: $(ENV_FILE)
	@echo "→ Starting Zroky self-host stack (postgres + redis + api + worker + dashboard)…"
	docker compose up -d --build postgres redis api worker beat dashboard
	@echo ""
	@echo "✓ Zroky is starting. Services:"
	@echo "  Dashboard : http://localhost:3000"
	@echo "  API       : http://localhost:8000"
	@echo "  API docs  : http://localhost:8000/docs"
	@echo ""
	@echo "Waiting for API to be healthy…"
	@timeout=120; elapsed=0; \
	until curl -fsS http://localhost:8000/health/live > /dev/null 2>&1; do \
	  sleep 3; elapsed=$$((elapsed+3)); \
	  if [ $$elapsed -ge $$timeout ]; then echo "ERROR: API did not become healthy in 120s"; exit 1; fi; \
	  printf "."; \
	done; echo ""
	@echo "✓ API healthy. Run 'make self-host-seed' to populate demo data."

$(ENV_FILE):
	@echo "→ Creating $(ENV_FILE) from example…"
	cp $(ENV_EXAMPLE) $(ENV_FILE)
	@echo "  Edit $(ENV_FILE) to add real API keys (OPENAI_API_KEY, GITHUB_TOKEN, etc.)"
	@echo "  Then re-run 'make self-host'."

## self-host-seed: load 1 K demo events into a running stack
self-host-seed:
	@echo "→ Seeding demo data…"
	docker compose exec api python scripts/seed_demo_data.py
	@echo "✓ Demo data loaded. Open http://localhost:3000 to explore."

## self-host-down: stop and remove containers (data volumes preserved)
self-host-down:
	docker compose down

## self-host-logs: follow logs for all services
self-host-logs:
	docker compose logs -f

## self-host-ps: show service status
self-host-ps:
	docker compose ps

## self-host-rebuild: rebuild images and restart (use after code changes)
self-host-rebuild:
	docker compose up -d --build

# ── CI / lint targets ────────────────────────────────────────────────────────

## capture-e2e-local: run Docker-free capture checks for gateway, backend, SDK, and dashboard
capture-e2e-local:
	python scripts/run_capture_e2e_local.py

## capture-smoke-local: run live Docker-free smoke with backend, gateway, and mock upstream
capture-smoke-local:
	python scripts/run_capture_smoke_no_docker.py

## lint-sizes: run file-size lint (Rule 3)
lint-sizes:
	python scripts/check_file_sizes.py

## api-contract-check: run API v1 breaking-change check (Rule 9)
api-contract-check:
	python scripts/check_api_v1_frozen.py

## schema-check: regenerate IngestEvent v2 artifacts and verify no drift (Rule 1)
schema-check:
	python scripts/gen_from_schema.py
	git diff --exit-code zroky-backend/app/schemas/ingest_event_v2.py \
	  zroky-dashboard/src/lib/ingest-types.ts \
	  zroky-backend/app/observability/otel_mapping.py

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo "Zroky Makefile targets:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  make /'
