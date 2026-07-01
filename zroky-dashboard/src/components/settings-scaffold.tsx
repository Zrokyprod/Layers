import type { ReactNode } from "react";

import {
  DashboardMetricStrip,
  DashboardVerdictHero,
  type DashboardMetricStripProps,
  type DashboardVerdictHeroProps,
} from "@/components/dashboard-scaffold";
import { cn } from "@/lib/utils";

export type SettingsScaffoldProps = {
  "aria-labelledby"?: string;
  children: ReactNode;
  className?: string;
};

export function SettingsScaffold({
  "aria-labelledby": ariaLabelledBy,
  children,
  className,
}: SettingsScaffoldProps) {
  return (
    <div
      className={cn("settings-control-page", className)}
      aria-labelledby={ariaLabelledBy}
    >
      {children}
    </div>
  );
}

export function SettingsHero(props: DashboardVerdictHeroProps) {
  return <DashboardVerdictHero {...props} className={cn("settings-control-hero", props.className)} />;
}

export function SettingsMetricStrip(props: DashboardMetricStripProps) {
  return <DashboardMetricStrip {...props} className={cn("settings-control-metrics", props.className)} />;
}

export type SettingsSectionProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  copy?: string;
  eyebrow?: string;
  id?: string;
  title: string;
};

export function SettingsSection({
  actions,
  children,
  className,
  copy,
  eyebrow,
  id,
  title,
}: SettingsSectionProps) {
  const headingId = id ? `${id}-title` : undefined;

  return (
    <section
      id={id}
      className={cn("settings-control-section", className)}
      aria-labelledby={headingId}
    >
      <header className="settings-control-section-header">
        <div>
          {eyebrow ? <span className="dashboard-eyebrow">{eyebrow}</span> : null}
          <h2 id={headingId}>{title}</h2>
          {copy ? <p>{copy}</p> : null}
        </div>
        {actions ? <div className="settings-control-section-actions">{actions}</div> : null}
      </header>
      <div className="settings-control-section-body">{children}</div>
    </section>
  );
}
