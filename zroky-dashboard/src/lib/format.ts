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
  timeZone: "UTC",
});

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
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

export function compactJson(value: unknown, fallback = "-"): string {
  if (value == null || value === "") {
    return fallback;
  }
  if (typeof value !== "object") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? JSON.stringify(value, null, 2) : "[]";
  }
  const entries = Object.entries(value as Record<string, unknown>).filter(
    ([, item]) => item != null && item !== "",
  );
  if (entries.length === 0) {
    return fallback;
  }
  return JSON.stringify(Object.fromEntries(entries), null, 2);
}

export function field(value: unknown, fallback = "-"): string {
  if (value == null || value === "") {
    return fallback;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function humanize(value: string | null | undefined, fallback = "-"): string {
  if (!value) {
    return fallback;
  }
  const normalized = value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) {
    return fallback;
  }
  return normalized.replace(/^\w/, (char) => char.toUpperCase());
}

export function timeSince(value: string | null | undefined, nowMs = Date.now()): string {
  if (!value) {
    return "-";
  }
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) {
    return "-";
  }
  const diff = Math.max(0, nowMs - time);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m old`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${hours}h old`;
  }
  return `${Math.floor(hours / 24)}d old`;
}

export function timeUntil(value: string | null | undefined, nowMs = Date.now()): string {
  if (!value) {
    return "-";
  }
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) {
    return "-";
  }
  const diff = time - nowMs;
  if (diff <= 0) {
    return "Expired";
  }
  const minutes = Math.ceil(diff / 60_000);
  if (minutes < 60) {
    return `${minutes}m left`;
  }
  const hours = Math.ceil(minutes / 60);
  if (hours < 48) {
    return `${hours}h left`;
  }
  return `${Math.ceil(hours / 24)}d left`;
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
