# Deployment Secrets Guide

This file defines where the provisioning token should live in production.

## Canonical Runtime Variable

- App runtime variable name: `PROVISIONING_TOKEN`

The backend reads this env var directly.

## Railway (Primary)

Railway does not use hierarchical secret paths. Use a project/service variable key.

- Location: Railway Dashboard -> Project -> Service -> Variables
- Key: `PROVISIONING_TOKEN`
- Value: your generated long random token

Use the same name in the API service that handles `/v1/projects*` endpoints.

## GCP (Migration Target)

Use Secret Manager object + Cloud Run env mapping.

- Secret name: `zroky-backend-provisioning-token`
- Full secret path format:
  `projects/<PROJECT_ID>/secrets/zroky-backend-provisioning-token/versions/latest`
- Cloud Run env var mapping:
  `PROVISIONING_TOKEN` <- Secret Manager secret above

## Recommended Production Pairing

- `REQUIRE_PROVISIONING_TOKEN=true`
- `PROVISIONING_TOKEN=<secret-manager-injected-value>`

## Quick Verification

1. Call `POST /v1/projects` without `X-Zroky-Admin-Token` -> should return `401`.
2. Call same endpoint with valid token header -> should return `201`.
