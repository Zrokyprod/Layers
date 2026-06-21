import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, DatabaseZap, FileJson, KeyRound, Plug, ShieldCheck, Terminal } from "lucide-react";

import { PublicInfoPage } from "@/components/public-info-page";

export const metadata: Metadata = {
  title: "Protected Agent Pilot | Zroky",
  description: "Run the Zroky design-partner install kit and prove a protected agent action end to end.",
};

const protectedSetupHref = "/signup?source=pilot&intent=protect-agent&plan=pro";
const dashboardSetupHref = "/settings/keys?intent=protect-agent&source=pilot&plan=pro";

const proofCards = [
  {
    Icon: ShieldCheck,
    title: "Pre-action stop",
    body: "Zroky captures the attempted high-stakes action and holds or blocks it before the commit point.",
  },
  {
    Icon: CheckCircle2,
    title: "System-of-record match",
    body: "The agent's claimed result is reconciled against a ledger or CRM record instead of trusting output text.",
  },
  {
    Icon: FileJson,
    title: "Exportable evidence",
    body: "The handoff ends with redacted JSON evidence and a stable evidence hash for buyer review.",
  },
];

const installCommands = [
  {
    label: "Refund / ledger proof",
    command:
      "python scripts/run_design_partner_install_kit.py --scenario refund --json --write-summary artifacts/design-partner-refund-summary.json --write-evidence artifacts/design-partner-refund-evidence.json",
  },
  {
    label: "Customer-record / CRM proof",
    command:
      "python scripts/run_design_partner_install_kit.py --scenario customer-record --json --write-summary artifacts/design-partner-crm-summary.json --write-evidence artifacts/design-partner-crm-evidence.json",
  },
];

const handoffSteps = [
  {
    Icon: KeyRound,
    title: "Create protected-agent key",
    body: "Open dashboard setup with pilot intent, choose the closest agent type, and copy the mandate plus SDK wrapper.",
    href: dashboardSetupHref,
    cta: "Open key setup",
  },
  {
    Icon: Plug,
    title: "Connect system of record",
    body: "Save a ledger/refund or CRM/customer connector once the partner gives a safe test record and API access.",
    href: "/settings/integrations#ledger-refund-connector",
    cta: "Open connector setup",
  },
  {
    Icon: DatabaseZap,
    title: "Run saved connector test",
    body: "Use the saved test endpoint so Zroky reads stored connector config instead of asking the customer to paste secrets into proof payloads.",
    href: "#saved-connector-tests",
    cta: "View test endpoints",
  },
  {
    Icon: FileJson,
    title: "Export evidence pack",
    body: "Open latest connector proof, confirm matched outcome and evidence hash, then download the redacted JSON pack.",
    href: "/settings/integrations#ledger-refund-connector",
    cta: "Open evidence proof",
  },
];

const savedConnectorTests = [
  {
    label: "Ledger/refund saved test endpoint",
    href: "/settings/integrations#ledger-refund-connector",
    command: `curl -X POST "$ZROKY_API_BASE/v1/integrations/system-of-record/ledger-refund/test" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "refund_id": "RF-1001",
    "claimed": {
      "refund_id": "RF-1001",
      "amount_usd": 42.18,
      "currency": "USD",
      "status": "posted"
    },
    "match_fields": ["refund_id", "amount_usd", "currency", "status"],
    "amount_usd": 42.18,
    "currency": "USD"
  }'`,
  },
  {
    label: "CRM/customer saved test endpoint",
    href: "/settings/integrations#customer-record-connector",
    command: `curl -X POST "$ZROKY_API_BASE/v1/integrations/system-of-record/customer-record/test" \\
  -H "x-api-key: $ZROKY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "customer_id": "CUS-1001",
    "claimed": {
      "customer_id": "CUS-1001",
      "email": "owner@example.com",
      "status": "active",
      "account_id": "acct_1001"
    },
    "match_fields": ["customer_id", "email", "status", "account_id"]
  }'`,
  },
];

const passCriteria = [
  "captured_call_linked",
  "unsafe_action_stopped",
  "connector_healthy",
  "saved_test_endpoint_used",
  "matched_outcome_shown",
  "evidence_hash_visible",
  "evidence_json_exported",
  "not_verified_when_missing",
  "evidence_pack_passed",
  "secrets_redacted",
];

export default function PilotPage() {
  return (
    <PublicInfoPage
      eyebrow="Design-partner pilot"
      title="Start with one protected agent and end with proof."
      summary="This is the customer handoff path for teams evaluating Zroky on a real high-stakes autonomous agent: run the install kit, show the blocked action, verify the real outcome, and export the evidence pack."
    >
      <div className="pilot-handoff-banner">
        <div>
          <strong>Paid-launch proof, not a generic demo.</strong>
          <p>
            Use this flow for a buyer who needs to believe Zroky can protect an agent that changes money,
            customer records, production systems, or customer communications.
          </p>
        </div>
        <div className="pilot-handoff-actions">
          <Link href={protectedSetupHref} className="public-info-cta">
            Start protected setup
          </Link>
          <Link href={dashboardSetupHref}>Open dashboard runbook</Link>
          <Link href="/#pricing">Back to pricing</Link>
        </div>
      </div>

      <h2>What the pilot proves</h2>
      <div className="pilot-proof-grid">
        {proofCards.map(({ Icon, title, body }) => (
          <article key={title}>
            <Icon aria-hidden="true" />
            <strong>{title}</strong>
            <p>{body}</p>
          </article>
        ))}
      </div>

      <h2>Dashboard handoff path</h2>
      <p>
        This is the route a design partner should follow after signup. It connects API-key setup, connector
        configuration, saved proof tests, and the Evidence Pack export into one buyer-readable sequence.
      </p>
      <div className="pilot-console-grid">
        {handoffSteps.map(({ Icon, title, body, href, cta }) => (
          <article key={title}>
            <Icon aria-hidden="true" />
            <strong>{title}</strong>
            <p>{body}</p>
            <Link href={href}>
              {cta}
              <ArrowRight aria-hidden="true" />
            </Link>
          </article>
        ))}
      </div>

      <h2>Run the install kit</h2>
      <p>
        Start local, then repeat against the partner&apos;s real ledger or CRM once API credentials and safe test
        records are ready.
      </p>
      <div className="pilot-command-list">
        {installCommands.map((item) => (
          <article key={item.label}>
            <span>
              <Terminal aria-hidden="true" />
              {item.label}
            </span>
            <code>{item.command}</code>
          </article>
        ))}
      </div>

      <h2 id="saved-connector-tests">Saved connector proof tests</h2>
      <p>
        These calls use the connector configuration already stored in Zroky. The copied payload should contain
        claim data and match fields only; raw system-of-record bearer tokens stay out of the UI and evidence.
      </p>
      <div className="pilot-endpoint-list">
        {savedConnectorTests.map((item) => (
          <article key={item.label}>
            <div>
              <span>{item.label}</span>
              <Link href={item.href}>
                Configure connector
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
            <code>{item.command}</code>
          </article>
        ))}
      </div>

      <h2>Pass criteria</h2>
      <p>
        The pilot handoff is a pass only when every check below is true. Missing evidence, mismatched outcome,
        or leaked secrets means the run is not verified.
      </p>
      <ul className="pilot-check-list">
        {passCriteria.map((criterion) => (
          <li key={criterion}>
            <CheckCircle2 aria-hidden="true" />
            <code>{criterion}</code>
          </li>
        ))}
      </ul>
      <p className="pilot-proof-note">
        Evidence Pack rule: <code>pass</code> needs a matched system-of-record outcome and visible evidence hash.
        Missing connector proof, a mismatch, or an unlinked runtime decision must stay <code>not_verified</code>.
      </p>

      <h2>Partner inputs for live smoke</h2>
      <p>
        Live smoke needs a Zroky API credential, one system-of-record API, a safe refund or customer record,
        and permission to export a redacted evidence pack. No raw partner token should appear in screenshots,
        summary files, or evidence artifacts.
      </p>
    </PublicInfoPage>
  );
}
