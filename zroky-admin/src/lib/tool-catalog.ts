import type { LucideIcon } from "lucide-react";
import { CheckCircle2, Database, GitBranch, Globe2, Headphones, Landmark, Mail, Route, ShieldCheck, ShoppingBag } from "lucide-react";

import type { OwnerToolImplementationStatus, OwnerToolRegistryItem } from "@/lib/owner-api";

export type ToolCatalogTone = "ok" | "warn" | "neutral";

export const TOOL_SUMMARY_ICONS = {
  available: CheckCircle2,
  template: GitBranch,
  planned: Globe2,
  default: Mail,
} as const;

export function toolStatusLabel(status: OwnerToolImplementationStatus | string): string {
  if (status === "available") return "Available";
  if (status === "template") return "Template";
  if (status === "planned") return "Planned";
  return status.replaceAll("_", " ");
}

export function toolStatusTone(status: OwnerToolImplementationStatus | string): ToolCatalogTone {
  if (status === "available") return "ok";
  if (status === "template") return "warn";
  return "neutral";
}

export function toolKindLabel(kind: OwnerToolRegistryItem["kind"]): string {
  if (kind === "runtime_path") return "Runtime path";
  if (kind === "verification_connector") return "Verification connector";
  return "Native tool family";
}

export function toolCategoryIcon(category: string, kind: OwnerToolRegistryItem["kind"]): LucideIcon {
  const normalized = category.toLowerCase();
  if (kind === "runtime_path") return Route;
  if (kind === "native_tool_family") return ShieldCheck;
  if (normalized.includes("payment") || normalized.includes("finance") || normalized.includes("ledger")) return Landmark;
  if (normalized.includes("commerce") || normalized.includes("shop")) return ShoppingBag;
  if (normalized.includes("crm") || normalized.includes("database") || normalized.includes("data")) return Database;
  if (normalized.includes("support") || normalized.includes("ticket") || normalized.includes("itsm")) return Headphones;
  if (normalized.includes("custom") || normalized.includes("rest") || normalized.includes("webhook")) return Globe2;
  return Mail;
}
