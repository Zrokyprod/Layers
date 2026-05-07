const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

const integer = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const shortDateTime = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
});

export function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "$0.00";
  }
  return usd.format(value);
}

export function formatCount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "0";
  }
  return integer.format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "0%";
  }
  return `${value.toFixed(2)}%`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }
  return shortDateTime.format(parsed);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }
  return shortDate.format(parsed);
}

export function safeString(value: unknown, fallback = "-"): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
  }
  return fallback;
}

export function numberFromUnknown(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return 0;
}
