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
    <section className={`approval-v2-kill-panel${armed ? " is-armed" : ""}`} aria-label="Runtime safety hold">
      <div>
        <span className="approval-v2-eyebrow">Emergency control</span>
        <strong>{armed ? "Confirm runtime safety hold" : "Runtime safety hold"}</strong>
        <p>Use this only when approval evidence, connectors, or policy boundaries look unreliable.</p>
      </div>
      {armed ? (
        <div className="approval-v2-kill-actions">
          <DashboardButton onClick={() => setArmed(false)} disabled={isPending} variant="soft">
            Cancel
          </DashboardButton>
          <DashboardButton icon={<ShieldAlert />} onClick={onConfirm} disabled={isPending} variant="primary">
            Confirm safety hold
          </DashboardButton>
        </div>
      ) : (
        <DashboardButton icon={<ShieldAlert />} onClick={() => setArmed(true)} disabled={isPending} variant="soft">
          Arm safety hold
        </DashboardButton>
      )}
    </section>
  );
}
