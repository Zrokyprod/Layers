import { test, expect, type Page } from "@playwright/test";

const stats = {
  total_users: 12,
  total_projects: 4,
  total_calls: 1000,
  calls_last_7d: 200,
  total_cost_usd: 100,
  cost_last_7d_usd: 10,
  new_users_last_7d: 2,
  active_users_last_7d: 6,
};

const health = {
  overall: "degraded",
  services: [
    { name: "PostgreSQL", status: "ok", detail: null, latency_ms: 4 },
    { name: "Redis", status: "degraded", detail: "slow ping", latency_ms: 80 },
    { name: "Celery", status: "down", detail: "No workers responding", latency_ms: null },
  ],
  exchange_rate: {
    cache_status: "ok",
    cache_rate: 83.2,
    cache_age_seconds: 12,
    cache_is_stale: false,
    cache_is_usable: true,
  },
  maintenance_mode: false,
  checked_at: "2026-06-05T12:00:00Z",
};

const infra = {
  worker_count: 0,
  worker_names: [],
  queues: [
    { queue_name: "diagnosis_fast", pending: 12, failed: 0 },
    { queue_name: "celery", pending: 3, failed: 1 },
  ],
  db_table_sizes: { calls: 1200, projects: 12, audit_logs: -1 },
};

const moneyPath = {
  generated_at: "2026-06-05T12:00:00Z",
  windows: { captures_hours: 24, replays_days: 7 },
  platform: {
    captures_24h: 80,
    issues_open: 2,
    replay_runs_7d: 5,
    verified_replay_runs_7d: 1,
    golden_traces_active: 3,
    ci_runs_7d: 4,
    ci_blocks_7d: 1,
    tenants_missing_provider_key: 1,
    tenants_near_replay_quota: 1,
    tenants_without_recent_capture: 0,
    last_deployed_smoke: {
      status: "failed",
      checked_at: "2026-06-05T11:55:00Z",
      project_id: "proj_demo",
      call_id: "call_smoke",
      golden_trace_id: "gt_smoke",
      ci_run_id: "ci_smoke",
      detail: "Latest deployed smoke CI gate failed.",
    },
  },
  tenants: [
    {
      project_id: "proj_demo",
      project_name: "Demo Tenant",
      plan_code: "pro",
      last_capture_at: "2026-06-05T11:30:00Z",
      captures_24h: 80,
      open_issue_count: 2,
      replay_run_count_7d: 5,
      verified_replay_count_7d: 1,
      golden_trace_count: 3,
      ci_run_count_7d: 4,
      blocking_ci_failures_7d: 1,
      provider_key_status: { state: "configured", active_provider_count: 1 },
      replay_quota_status: { state: "near_limit", enabled: true, used: 90, limit: 100, resets_at: "2026-07-01" },
      next_owner_action: "review_blocked_ci",
    },
  ],
};

const billingSummary = {
  total_subscriptions: 2,
  overdue: 0,
  canceled: 0,
  by_plan: [{ plan: "Pro", slug: "pro", tenant_count: 2 }],
  by_status: [{ status: "active", count: 2 }],
};

const pricing = { config: {}, path: "redis", exists: true };

const pricingPlans = {
  schema_version: "1.0",
  source_of_truth: "api-contracts/pricing-plans.json",
  currency: "USD",
  unlimited: -1,
  canonical_plan_order: ["free", "pilot", "pro", "enterprise"],
  aliases: { plus: "pro" },
  drift: [],
  plans: [
    {
      code: "pro",
      name: "Pro",
      price: { label: "$99", monthly_usd: 99, period: "/mo" },
      description: "Release protection.",
      note: "Main release plan.",
      featured: true,
      pricing: {
        calls_per_month: 3000000,
        retention_days: 90,
        replay_credits: 1000,
        golden_traces: 1000,
        golden_sets: 50,
        non_blocking_ci: true,
        blocking_ci: true,
        provider_key_vault: false,
      },
      enforcement: { limits: {}, entitlements: {}, compatibility: {} },
    },
  ],
};

const billingAccounts = {
  total: 1,
  items: [
    {
      org_id: "proj_demo",
      project_name: "Demo Tenant",
      plan_code: "pro",
      status: "active",
      sla_tier: "team",
      seats: 5,
      current_period_end: "2026-07-01T00:00:00Z",
      trial_end: null,
      updated_at: "2026-06-05T00:00:00Z",
    },
  ],
};

const supportTickets = {
  total: 1,
  items: [
    {
      ticket_id: "ticket_1",
      tenant_id: "proj_demo",
      user_id: "user_1",
      subject: "email:user@example.com",
      email: "user@example.com",
      title: "Replay gate failed",
      description: "CI gate failed after the prompt change.",
      category: "ci",
      priority: "high",
      status: "open",
      assigned_to: null,
      resolved_at: null,
      created_at: "2026-06-05T10:00:00Z",
      updated_at: "2026-06-05T11:00:00Z",
      message_count: 2,
    },
  ],
};

const supportDetail = {
  ticket: supportTickets.items[0],
  messages: [
    {
      message_id: "msg_1",
      sender_type: "user",
      sender_subject: "email:user@example.com",
      body: "The CI gate is blocking my PR.",
      is_internal: false,
      created_at: "2026-06-05T10:00:00Z",
    },
  ],
};

const auditLog = {
  total: 2,
  entries: [
    {
      id: "audit_1",
      tenant_id: "proj_demo",
      diagnosis_id: "diag_1",
      action: "owner.tenant.rate_limit.set",
      actor_subject: "owner@example.com",
      metadata_json: "{\"target_id\":\"proj_demo\"}",
      created_at: "2026-06-05T10:00:00Z",
    },
    {
      id: "audit_2",
      tenant_id: "PLATFORM",
      diagnosis_id: "owner_action",
      action: "owner.broadcast",
      actor_subject: "owner@example.com",
      metadata_json: "{}",
      created_at: "2026-06-05T11:00:00Z",
    },
  ],
};

const projects = {
  total: 1,
  projects: [
    {
      id: "proj_demo",
      name: "Demo Tenant",
      owner_ref: "owner_demo",
      is_active: true,
      created_at: "2026-06-05T10:00:00Z",
      call_count: 200,
      total_cost_usd: 42,
      member_count: 3,
    },
  ],
};

const projectDetail = projects.projects[0];
const projectMembers = {
  members: [
    {
      membership_id: "mem_1",
      user_id: "user_1",
      email: "owner@example.com",
      github_login: null,
      display_name: null,
      role: "owner",
      is_active: true,
      joined_at: "2026-06-05T10:00:00Z",
    },
  ],
};
const projectRateLimit = {
  project_id: "proj_demo",
  has_override: true,
  overrides: {
    ingest_soft_limit_rpm: 300,
    ingest_burst_limit_rpm: 600,
    ingest_enforce_rate_limit: true,
  },
};

async function mockOwnerApi(page: Page) {
  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });

  await page.route("**/api/owner/session", (route) => route.fulfill(json({ ok: true })));
  await page.route("**/api/zroky/v1/owner/stats", (route) => route.fulfill(json(stats)));
  await page.route("**/api/zroky/v1/owner/health", (route) => route.fulfill(json(health)));
  await page.route("**/api/zroky/v1/owner/infra", (route) => route.fulfill(json(infra)));
  await page.route("**/api/zroky/v1/owner/money-path-health", (route) => route.fulfill(json(moneyPath)));
  await page.route("**/api/zroky/v1/owner/billing/summary", (route) => route.fulfill(json(billingSummary)));
  await page.route("**/api/zroky/v1/owner/pricing/plans", (route) => route.fulfill(json(pricingPlans)));
  await page.route("**/api/zroky/v1/owner/pricing", (route) => route.fulfill(json(pricing)));
  await page.route("**/api/zroky/v1/owner/billing/accounts**", (route) => route.fulfill(json(billingAccounts)));
  await page.route("**/api/zroky/v1/owner/support/tickets/ticket_1", (route) => route.fulfill(json(supportDetail)));
  await page.route("**/api/zroky/v1/owner/support/tickets**", (route) => route.fulfill(json(supportTickets)));
  await page.route("**/api/zroky/v1/owner/audit-log**", (route) => route.fulfill(json(auditLog)));
  await page.route("**/api/zroky/v1/owner/projects/proj_demo/members", (route) => route.fulfill(json(projectMembers)));
  await page.route("**/api/zroky/v1/owner/projects/proj_demo/rate-limit", (route) => route.fulfill(json(projectRateLimit)));
  await page.route("**/api/zroky/v1/owner/projects/proj_demo", (route) => route.fulfill(json(projectDetail)));
  await page.route("**/api/zroky/v1/owner/projects?**", (route) => route.fulfill(json(projects)));
}

test.describe("Owner Dashboard", () => {
  test("owner login requires provisioning token", async ({ page }) => {
    await page.goto("/owner");
    // Should redirect or show auth prompt when no token is present
    await expect(page.locator("body")).toContainText(/login|token|unauthorized/i);
  });

  test("product proof routes render real owner evidence without page overflow", async ({ page }) => {
    await mockOwnerApi(page);

    const routes: Array<{ path: string; text: string[] }> = [
      { path: "/owner", text: ["Regression Firewall Health", "Deployment Smoke", "Latest deployed smoke CI gate failed."] },
      { path: "/owner/money-path", text: ["Money Path", "Demo Tenant", "Blocked CI Evidence"] },
      { path: "/owner/projects/proj_demo", text: ["Regression Firewall", "Review blocked CI", "90 / 100"] },
      { path: "/owner/pricing", text: ["Revenue & Entitlements", "Plan Entitlement Matrix", "Replay quota"] },
      { path: "/owner/ops", text: ["Founder Ops Console", "Deployed Smoke Proof", "ci_smoke"] },
      { path: "/owner/infrastructure", text: ["Infrastructure Health", "Ops Health Proof", "ci_smoke"] },
      { path: "/owner/support", text: ["Support", "Product Evidence", "Provider: configured (1)"] },
      { path: "/owner/audit", text: ["Audit Log", "Product Evidence", "Platform event"] },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      for (const expected of route.text) {
        await expect(page.locator("body")).toContainText(expected);
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(2);
    }
  });
});
