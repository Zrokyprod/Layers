import { statusLabel, type ActionStatusKind, type StatusTone } from "@/lib/action-status";

type StatusPillProps = {
  value: string | null | undefined;
  kind?: ActionStatusKind;
  label?: string;
  tone?: StatusTone;
  title?: string;
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export function StatusPill({ value, kind, label, tone, title }: StatusPillProps) {
  const safe = value && value.trim() ? value.trim() : "unknown";
  const css = normalize(safe);
  const display = label ?? (kind ? statusLabel(safe, kind) : safe);
  return (
    <span
      className={`status-pill status-${css}${tone ? ` status-tone-${tone}` : ""}`}
      data-tone={tone}
      title={title}
    >
      {display}
    </span>
  );
}
