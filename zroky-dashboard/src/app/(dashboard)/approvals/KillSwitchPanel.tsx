"use client";

import { ShieldAlert } from "lucide-react";

import { DashboardButton } from "@/components/dashboard-button";

type KillSwitchPanelProps = {
  armed: boolean;
  setArmed: (value: boolean) => void;
  isPending: boolean;
  onConfirm: () => void;
};

export function KillSwitchPanel({
  armed,
  isPending,
  onConfirm,
  setArmed,
}: KillSwitchPanelProps) {
  return (
    <section className={`approval-v2-kill-panel${armed ? " is-armed" : ""}`} aria-label="Runtime kill switch">
      <div>
        <span className="approval-v2-eyebrow">Runtime kill switch</span>
        <strong>{armed ? "Confirm global runtime hold" : "Fail closed when proof is unsafe"}</strong>
        <p>Pause high-risk runtime approvals when evidence, connector, or mandate boundaries are unreliable.</p>
      </div>
      {armed ? (
        <div className="approval-v2-kill-actions">
          <DashboardButton onClick={() => setArmed(false)} disabled={isPending} variant="soft">
            Cancel
          </DashboardButton>
          <DashboardButton icon={<ShieldAlert />} onClick={onConfirm} disabled={isPending} variant="primary">
            Confirm kill switch
          </DashboardButton>
        </div>
      ) : (
        <DashboardButton icon={<ShieldAlert />} onClick={() => setArmed(true)} disabled={isPending} variant="soft">
          Arm kill switch confirmation
        </DashboardButton>
      )}
    </section>
  );
}
