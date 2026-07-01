import { DashboardMetricStrip } from "@/components/dashboard-scaffold";

export type EvidenceProofMetric = {
  detail: string;
  href: string;
  label: string;
  tone: "danger" | "neutral" | "success" | "warning";
  value: string;
};

type EvidenceProofStripProps = {
  metrics: EvidenceProofMetric[];
  onMetricClick?: (href: string) => void;
};

export function EvidenceProofStrip({ metrics, onMetricClick }: EvidenceProofStripProps) {
  return (
    <DashboardMetricStrip
      ariaLabel="Evidence proof summary"
      columns={4}
      metrics={metrics.map((metric) => ({
        helper: metric.detail,
        href: metric.href,
        label: metric.label,
        tone: metric.tone,
        value: metric.value,
      }))}
      onMetricClick={onMetricClick ? (metric) => onMetricClick(metric.href ?? "/evidence") : undefined}
    />
  );
}
