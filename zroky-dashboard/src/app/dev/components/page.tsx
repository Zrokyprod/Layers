import { notFound } from "next/navigation";
import { ArrowRight, KeyRound, RefreshCw, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { DashboardButton, DashboardButtonLink } from "@/components/dashboard-button";
import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  DashboardWorkspace,
} from "@/components/dashboard-scaffold";
import { ProofChainStepper } from "@/components/proof-chain-stepper";
import {
  SettingsHero,
  SettingsMetricStrip,
  SettingsScaffold,
  SettingsSection,
} from "@/components/settings-scaffold";
import { StatusPill } from "@/components/status-pill";
import type { ProofChainStep } from "@/lib/action-view";

const proofChain: ProofChainStep[] = [
  {
    step: "action",
    label: "Action",
    status: "Authorized",
    tone: "success",
    detail: "Intent accepted",
  },
  {
    step: "policy",
    label: "Policy",
    status: "Allowed",
    tone: "success",
    detail: "Policy passed",
  },
  {
    step: "execution",
    label: "Execution",
    status: "Awaiting runner",
    tone: "warning",
    detail: "Runner not claimed",
  },
  {
    step: "verification",
    label: "Verification",
    status: "Mismatched",
    tone: "danger",
    detail: "Source of record differs",
  },
  {
    step: "receipt",
    label: "Receipt",
    status: "Generated",
    tone: "success",
    detail: "Signed receipt exists",
  },
];

function PreviewPanel({
  children,
  eyebrow,
  title,
}: {
  children: ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <section className="visual-gate-panel">
      <div>
        <span className="visual-gate-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export default function DevComponentsPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <div className="app-shell visual-gate-shell" data-dashboard-system="control-v1">
      <main className="visual-gate-page" aria-labelledby="visual-gate-title">
        <header className="visual-gate-hero">
          <div>
            <span className="visual-gate-eyebrow">Dev visual gate</span>
            <h1 id="visual-gate-title">Dashboard component preview</h1>
            <p>
              Auth-free mock surface for CSS screenshot checks. Use it before color, token, or layout
              migrations.
            </p>
          </div>
          <StatusPill value="not_recorded" label="Dev only" tone="neutral" />
        </header>

        <section className="visual-gate-grid" aria-label="Proof chain stepper variants">
          <PreviewPanel eyebrow="Actions" title="Compact proof chain">
            <ProofChainStepper steps={proofChain} variant="compact" />
          </PreviewPanel>

          <PreviewPanel eyebrow="Approvals" title="Compact approval chain">
            <ProofChainStepper steps={proofChain} variant="compact" />
          </PreviewPanel>

          <PreviewPanel eyebrow="Evidence" title="Evidence proof chain">
            <div className="evidence-ledger-page">
              <ProofChainStepper steps={proofChain} variant="evidence" />
            </div>
          </PreviewPanel>

          <PreviewPanel eyebrow="Agents" title="Default fleet chain">
            <ProofChainStepper steps={proofChain} />
          </PreviewPanel>

          <PreviewPanel eyebrow="Agent drill" title="Default detail chain">
            <ProofChainStepper steps={proofChain} />
          </PreviewPanel>
        </section>

        <section className="visual-gate-grid visual-gate-grid-small" aria-label="Token and status samples">
          <PreviewPanel eyebrow="Status" title="Pill tones">
            <div className="visual-gate-pill-row">
              <StatusPill value="matched" kind="proof" tone="success" />
              <StatusPill value="not_verified" kind="proof" tone="warning" />
              <StatusPill value="mismatched" kind="proof" tone="danger" />
              <StatusPill value="pending" kind="proof" tone="neutral" />
            </div>
          </PreviewPanel>

          <PreviewPanel eyebrow="Cards" title="Mission-control surface">
            <div className="visual-gate-card-row">
              <div className="visual-gate-metric" data-tone="success">
                <span>Export-ready</span>
                <strong>18</strong>
              </div>
              <div className="visual-gate-metric" data-tone="danger">
                <span>Exceptions</span>
                <strong>2</strong>
              </div>
            </div>
          </PreviewPanel>
        </section>

        <section className="visual-gate-grid" aria-label="Dashboard scaffold primitives">
          <PreviewPanel eyebrow="Hero" title="Verdict surface">
            <DashboardVerdictHero
              eyebrow="Actions"
              title="Actions controlled"
              copy="Protected action lifecycle, runner execution, proof, and receipts are visible."
              pill="5 controlled"
              tone="success"
              updatedLabel="Updated live"
              actions={(
                <>
                  <DashboardButton icon={<RefreshCw />} variant="soft">
                    Refresh
                  </DashboardButton>
                  <DashboardButtonLink href="/dev/components" variant="primary">
                    Open receipts
                  </DashboardButtonLink>
                </>
              )}
            />
          </PreviewPanel>

          <PreviewPanel eyebrow="Metrics" title="Metric strip">
            <DashboardMetricStrip
              ariaLabel="Preview metrics"
              columns={3}
              metrics={[
                {
                  helper: "Action intents routed through the kernel.",
                  label: "Protected actions",
                  tone: "success",
                  value: "5",
                },
                {
                  helper: "One action needs proof review.",
                  label: "Needs proof",
                  tone: "warning",
                  value: "1",
                },
                {
                  helper: "No source mutations bypassed control.",
                  label: "Bypass risk",
                  tone: "success",
                  value: "0",
                },
              ]}
            />
          </PreviewPanel>

          <PreviewPanel eyebrow="Workspace" title="60/40 cockpit grid">
            <DashboardWorkspace
              left={(
                <div className="visual-gate-workspace-panel">
                  <strong>Lifecycle queue</strong>
                  <p>Primary list surface.</p>
                </div>
              )}
              right={(
                <div className="visual-gate-workspace-panel">
                  <strong>Selected proof</strong>
                  <p>Focused inspector rail.</p>
                </div>
              )}
            />
          </PreviewPanel>
        </section>

        <section className="visual-gate-grid" aria-label="Settings scaffold primitives">
          <PreviewPanel eyebrow="Settings" title="Control-plane settings shell">
            <SettingsScaffold>
              <SettingsHero
                eyebrow="API Keys"
                title="Verified action access"
                copy="Create a key, route the first protected action, and confirm the signed receipt."
                pill="Launch loop"
                tone="success"
                updatedLabel="Ready"
                actions={(
                  <DashboardButton variant="primary" icon={<KeyRound />}>
                    Create key
                  </DashboardButton>
                )}
              />
              <SettingsMetricStrip
                ariaLabel="Settings preview metrics"
                columns={3}
                metrics={[
                  {
                    helper: "Keys available for SDK and gateway access.",
                    label: "Active keys",
                    tone: "success",
                    value: "2",
                  },
                  {
                    helper: "Protected agents allowed by the current plan.",
                    label: "Agent cap",
                    tone: "neutral",
                    value: "3",
                  },
                  {
                    helper: "Verifier connectors ready for proof.",
                    label: "Verifier health",
                    tone: "warning",
                    value: "1 gap",
                  },
                ]}
              />
              <SettingsSection
                eyebrow="Access"
                title="Create project key"
                copy="Keys unlock the SDK. Agent authority stays in Agent Setup and Policies."
                actions={<DashboardButton variant="soft">Rotate</DashboardButton>}
              >
                <p>One-time key reveal and rotation controls sit inside this section.</p>
              </SettingsSection>
            </SettingsScaffold>
          </PreviewPanel>
        </section>

        <section className="visual-gate-grid visual-gate-grid-small" aria-label="Button primitive samples">
          <PreviewPanel eyebrow="Buttons" title="Canonical actions">
            <div className="visual-gate-button-row">
              <DashboardButton variant="primary" icon={<RefreshCw />}>
                Refresh
              </DashboardButton>
              <DashboardButtonLink href="/dev/components" variant="soft" icon={<ArrowRight />} iconPosition="right">
                Open preview
              </DashboardButtonLink>
              <DashboardButton variant="ghost">Dismiss</DashboardButton>
              <DashboardButton variant="danger" icon={<Trash2 />}>
                Delete
              </DashboardButton>
            </div>
          </PreviewPanel>

          <PreviewPanel eyebrow="States" title="Sizes and disabled">
            <div className="visual-gate-button-row">
              <DashboardButton size="sm" variant="soft">
                Small
              </DashboardButton>
              <DashboardButton aria-label="Icon refresh" icon={<RefreshCw />} size="icon" variant="soft" />
              <DashboardButton disabled variant="primary">
                Disabled
              </DashboardButton>
              <DashboardButton loading variant="soft">
                Loading
              </DashboardButton>
            </div>
          </PreviewPanel>
        </section>
      </main>
    </div>
  );
}
