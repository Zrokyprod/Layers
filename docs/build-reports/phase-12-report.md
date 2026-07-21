# Zroky Phase 12 Build Report

Status: Complete
Phase: Verification Connector Fabric
Tracker IDs: P12-001 to P12-008

## Scope

Phase 12 makes Zroky system-agnostic without hand-building every SaaS connector. The implementation uses three proof primitives plus branded manifest presets:

- Generic REST / OpenAPI read
- Webhook callback
- Postgres / SQL read

Branded connectors are manifest presets first, not bespoke runtime code.

## Completed IDs

- P12-001 Connector manifest contract.
- P12-002 Registry-to-manifest wiring.
- P12-003 Read-only manifest validation.
- P12-004 Generic REST and Postgres proof by manifest.
- P12-005 Branded verification presets.
- P12-006 Manifest-driven connector UI contract.
- P12-007 Signed webhook callback observation intake.
- P12-008 Keyless two-family connector proof.

## Changed Code

- Added connector manifest schema and validation under `zroky-backend/app/domain/connector_manifest/`.
- Added manifest runtime adapter that executes Generic REST and Postgres manifests through existing relay code.
- Added read-only branded presets for Stripe, GitHub, Jira, ServiceNow, Salesforce, HubSpot, Zendesk, and Shopify.
- Added `manifest_id` to existing `ToolRegistryItem` rows and `/v1/tools/registry` responses.
- Added ServiceNow as a template registry preset backed by a manifest, without adding a legacy DB connector enum or bespoke service path.
- Extended Generic REST relay reads to support manifest-declared path keys, used by GitHub-style `owner/repo` paths.
- Added signed inbound webhook callback observation intake for the push-based `webhook_callback` primitive.
- Added keyless two-family proof: one Generic REST source and one SQL source feed one verified outcome graph through manifest runtime.
- Updated dashboard connector inventory to read manifest IDs from the backend registry and show them in connector details.

## Tests And Checks

- `python -m pytest tests/test_connector_manifest.py -q` passed.
- `python -m pytest tests/test_tool_registry_routes.py -q` passed.
- `python -m pytest tests/test_connector_manifest.py tests/test_final_relay_protocol.py -q` passed.
- `python -m pytest tests/test_connector_manifest.py tests/test_connector_manifest_presets.py tests/test_final_relay_protocol.py tests/test_tool_registry_routes.py -q` passed.
- `python -m pytest tests/test_final_intents_api.py::test_signed_webhook_callback_creates_immutable_observation tests/test_final_intents_api.py::test_webhook_callback_rejects_bad_signature tests/test_final_intents_api.py::test_webhook_callback_fails_closed_when_secret_unset -q` passed.
- `python -m pytest tests/test_connector_manifest_keyless_proof.py -q` passed.
- Backend connector manifest, relay, registry, and agent-profile compile checks passed.
- `npm test -- --run src/lib/connector-inventory.test.ts` passed.
- `npm test -- --run src/lib/connector-inventory.test.ts 'src/app/(dashboard)/integrations/page.test.tsx'` passed.
- `npm test -- --run src/lib/api.test.ts` passed.
- `powershell -ExecutionPolicy Bypass -File 'D:\Zroky AI\scripts\verify_zroky_build_plan.ps1'` passed.

## Known Risks

- Presets are not full one-click OAuth installs yet. They are read-only manifest contracts plus registry/dashboard visibility.
- ServiceNow is a template manifest only; no old SOR DB enum or native ServiceNow config route was added.
- Webhook callback now has signed inbound observation intake; no webhook installer UI was added in Phase 12.
- Dashboard shows manifest IDs and uses registry metadata; it does not yet install or edit manifest presets.
- Real credential validation still requires design-partner keys or test tenants.
- Generic REST keyless proof uses the existing HTTP transport seam to preserve the HTTPS/private-host safety invariant; real SaaS reads still require customer credentials.

## Decision

P12-001 through P12-008 are complete. The connector layer is now manifest-first: three primitives, branded presets, read-only validation, signed webhook intake, keyless two-family proof, and dashboard visibility.
