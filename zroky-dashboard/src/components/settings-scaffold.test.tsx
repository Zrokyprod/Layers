import { render, screen } from "@testing-library/react";
import { KeyRound } from "lucide-react";
import { describe, expect, it } from "vitest";

import { DashboardButton } from "@/components/dashboard-button";
import {
  SettingsHero,
  SettingsMetricStrip,
  SettingsScaffold,
  SettingsSection,
} from "@/components/settings-scaffold";

describe("Settings scaffold", () => {
  it("renders settings surfaces through shared dashboard primitives", () => {
    const { container } = render(
      <SettingsScaffold aria-labelledby="settings-title">
        <SettingsHero
          eyebrow="Settings"
          title="API Keys"
          copy="Create a key, run a verified action, and see the first receipt."
          tone="success"
          pill="Control ready"
          icon={<KeyRound />}
          actions={<DashboardButton variant="primary">Create key</DashboardButton>}
        />
        <SettingsMetricStrip
          ariaLabel="Settings metrics"
          columns={2}
          metrics={[
            {
              helper: "SDK and gateway credentials.",
              label: "Active keys",
              tone: "success",
              value: "2",
            },
            {
              helper: "Plan cap visible before setup.",
              label: "Agent cap",
              tone: "neutral",
              value: "3",
            },
          ]}
        />
        <SettingsSection
          eyebrow="Access"
          title="Create project key"
          copy="Keys unlock SDK access; policy remains in Agent Setup."
          actions={<DashboardButton variant="soft">Rotate</DashboardButton>}
        >
          <p>One-time reveal stays inside the page.</p>
        </SettingsSection>
      </SettingsScaffold>,
    );

    expect(screen.getByRole("heading", { name: "API Keys" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create key" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Settings metrics" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Create project key" })).toBeInTheDocument();

    expect(container.querySelector(".settings-control-page")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-hero.dashboard-verdict-hero")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-metrics.dashboard-metric-strip")).toBeInTheDocument();
    expect(container.querySelector(".settings-control-section")).toBeInTheDocument();
  });
});
