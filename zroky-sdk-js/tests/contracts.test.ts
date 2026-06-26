// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import {
  PHASE1_NATIVE_TOOL_FAMILIES,
  PHASE1_RISKY_ACTION_TYPES,
  PHASE1_RUNTIME_PATHS,
  PHASE1_VERIFICATION_CONNECTORS,
  ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION,
} from "../src";
import type { ZrokyConnectorTemplate, ZrokyToolActionPassport } from "../src";

type SchemaDef = {
  enum?: string[];
  required?: string[];
  properties?: Record<string, SchemaDef>;
};

type AgentToolControlSchema = {
  $defs: Record<string, SchemaDef>;
};

async function loadSchema(): Promise<AgentToolControlSchema> {
  const raw = await readFile(
    new URL("../../api-contracts/agent-tool-control-v1.schema.json", import.meta.url),
    "utf8",
  );
  return JSON.parse(raw) as AgentToolControlSchema;
}

function schemaEnum(schema: AgentToolControlSchema, defName: string): string[] {
  const values = schema.$defs[defName]?.enum;
  assert.ok(values, `${defName} enum should exist in schema`);
  return values;
}

describe("agent tool control contracts", () => {
  it("keeps public SDK constants aligned with the canonical schema", async () => {
    const schema = await loadSchema();

    assert.deepEqual(
      [...PHASE1_RISKY_ACTION_TYPES],
      schemaEnum(schema, "RiskActionType"),
    );
    assert.deepEqual([...PHASE1_RUNTIME_PATHS], schemaEnum(schema, "RuntimePath"));
    assert.deepEqual(
      [...PHASE1_VERIFICATION_CONNECTORS],
      schemaEnum(schema, "VerificationConnectorType"),
    );
    assert.deepEqual([...PHASE1_NATIVE_TOOL_FAMILIES], schemaEnum(schema, "NativeToolFamily"));
  });

  it("documents the existing guard payload as a tool action passport", async () => {
    const schema = await loadSchema();
    const required = schema.$defs.ToolActionPassport.required ?? [];
    const properties = schema.$defs.ToolActionPassport.properties ?? {};

    assert.ok(required.includes("action_type"));
    assert.ok("tool_name" in properties);
    assert.ok("tool_args" in properties);
    assert.ok("external_action" in properties);
    assert.ok("approval_id" in properties);
    assert.ok("business_impact" in properties);
    assert.ok("impact_usd" in properties);

    const passport: ZrokyToolActionPassport = {
      schema_version: ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION,
      action_type: "refund",
      tool_name: "stripe.refunds.create",
      tool_args: {
        payment_intent: "pi_123",
        amount: 4900,
      },
      trace_id: "trace_123",
      call_id: "call_123",
      agent_name: "refund-agent",
      runtime_path: "sdk",
      external_action: true,
      business_impact_summary: "Issue customer refund",
      impact_usd: 49,
      order_id: "ord_123",
    };

    const body = JSON.parse(JSON.stringify(passport)) as Record<string, unknown>;
    assert.equal(body.schema_version, ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION);
    assert.equal(body.action_type, "refund");
    assert.equal(body.tool_name, "stripe.refunds.create");
    assert.equal(body.external_action, true);
    assert.equal(body.impact_usd, 49);
  });

  it("covers the Phase 1 native tool families through connector templates", () => {
    const templates: ZrokyConnectorTemplate[] = [
      {
        connector_type: "ledger_refund",
        native_tool_family: "stripe_refund",
        display_name: "Stripe refunds",
        purpose: "verify",
        auth_mode: "api_key",
        supported_action_types: ["refund"],
      },
      {
        connector_type: "crm_record",
        native_tool_family: "hubspot_customer",
        display_name: "HubSpot customer records",
        purpose: "verify",
        auth_mode: "oauth2",
        supported_action_types: ["customer_record_update"],
      },
      {
        connector_type: "ticket_status",
        native_tool_family: "zendesk_ticket",
        display_name: "Zendesk ticket status",
        purpose: "verify",
        auth_mode: "oauth2",
        supported_action_types: ["ticket_close"],
      },
      {
        connector_type: "email_delivery",
        native_tool_family: "sendgrid_email",
        display_name: "SendGrid delivery",
        purpose: "verify",
        auth_mode: "api_key",
        supported_action_types: ["email_send"],
      },
      {
        connector_type: "github_ci",
        native_tool_family: "github_pr_ci_deploy",
        display_name: "GitHub PR, CI, and deploy checks",
        purpose: "verify",
        auth_mode: "oauth2",
        supported_action_types: ["deploy_change"],
      },
    ];

    const coveredFamilies = new Set(templates.map((template) => template.native_tool_family));
    assert.ok(coveredFamilies.has("stripe_refund"));
    assert.ok(coveredFamilies.has("hubspot_customer"));
    assert.ok(coveredFamilies.has("zendesk_ticket"));
    assert.ok(coveredFamilies.has("sendgrid_email"));
    assert.ok(coveredFamilies.has("github_pr_ci_deploy"));
  });
});
