type StatusPillProps = {
  value: string | null | undefined;
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export function StatusPill({ value }: StatusPillProps) {
  const safe = value && value.trim() ? value.trim() : "unknown";
  const css = normalize(safe);
  return <span className={`status-pill status-${css}`}>{safe}</span>;
}
