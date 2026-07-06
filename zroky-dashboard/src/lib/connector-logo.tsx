import type { ComponentType } from "react";
import { Database, Globe, Landmark, Receipt, Users } from "lucide-react";
import {
  SiGithub,
  SiHubspot,
  SiIntercom,
  SiJira,
  SiPostgresql,
  SiRazorpay,
  SiSalesforce,
  SiShopify,
  SiSlack,
  SiStripe,
  SiZendesk,
  SiZoho,
} from "react-icons/si";

import type { ConnectorInventoryId } from "@/lib/connector-inventory";

type LogoDef = {
  Icon: ComponentType<{ size?: number; className?: string }>;
  color: string;
  branded: boolean;
};

// Brand marks for connectors that map to a known system of record. Generic /
// template / SQL paths fall back to a neutral Zroky-tinted glyph so every
// connector still reads as a first-class tile.
const CONNECTOR_LOGOS: Record<ConnectorInventoryId, LogoDef> = {
  stripe_refund: { Icon: SiStripe, color: "#635BFF", branded: true },
  stripe_payment: { Icon: SiStripe, color: "#635BFF", branded: true },
  razorpay_refund: { Icon: SiRazorpay, color: "#3395FF", branded: true },
  shopify_admin: { Icon: SiShopify, color: "#95BF47", branded: true },
  salesforce_crm: { Icon: SiSalesforce, color: "#00A1E0", branded: true },
  hubspot_crm: { Icon: SiHubspot, color: "#FF7A59", branded: true },
  zoho_crm: { Icon: SiZoho, color: "#E42527", branded: true },
  zendesk_ticket: { Icon: SiZendesk, color: "#03363D", branded: true },
  intercom: { Icon: SiIntercom, color: "#1F8DED", branded: true },
  jira_issue: { Icon: SiJira, color: "#2684FF", branded: true },
  postgres_read: { Icon: SiPostgresql, color: "#4169E1", branded: true },
  github: { Icon: SiGithub, color: "#181717", branded: true },
  slack: { Icon: SiSlack, color: "#4A154B", branded: true },
  netsuite_finance: { Icon: Landmark, color: "#1F6FEB", branded: false },
  generic_rest: { Icon: Globe, color: "#635BFF", branded: false },
  ledger_template: { Icon: Receipt, color: "#635BFF", branded: false },
  customer_template: { Icon: Users, color: "#635BFF", branded: false },
};

const FALLBACK_LOGO: LogoDef = { Icon: Database, color: "#635BFF", branded: false };

export function ConnectorLogo({
  id,
  size = 20,
}: {
  id: ConnectorInventoryId;
  size?: number;
}) {
  const { Icon, color } = CONNECTOR_LOGOS[id] ?? FALLBACK_LOGO;
  return (
    <span
      className="connector-logo"
      style={{ ["--connector-brand" as string]: color }}
      aria-hidden="true"
    >
      <Icon size={size} />
    </span>
  );
}
