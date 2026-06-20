import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, FileJson, ShieldCheck, Terminal } from "lucide-react";

import { PublicInfoPage } from "@/components/public-info-page";

export const metadata: Metadata = {
  title: "Protected Agent Pilot | Zroky",
  description: "Run the Zroky design-partner install kit and prove a protected agent action end to end.",
};

const protectedSetupHref = "/signup?source=pilot&intent=protect-agent&plan=pro";

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

const passCriteria = [
  "captured_call_linked",
  "unsafe_action_stopped",
  "matched_outcome_shown",
  "evidence_hash_visible",
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

      <h2>Partner inputs for live smoke</h2>
      <p>
        Live smoke needs a Zroky API credential, one system-of-record API, a safe refund or customer record,
        and permission to export a redacted evidence pack. No raw partner token should appear in screenshots,
        summary files, or evidence artifacts.
      </p>
    </PublicInfoPage>
  );
}
