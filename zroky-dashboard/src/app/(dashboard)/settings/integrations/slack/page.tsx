import { redirect } from "next/navigation";

export default function SettingsSlackIntegrationRedirectPage() {
  redirect("/integrations/slack");
}
