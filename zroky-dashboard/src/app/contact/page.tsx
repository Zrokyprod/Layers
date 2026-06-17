import type { Metadata } from "next";

import { PublicInfoPage } from "@/components/public-info-page";

export const metadata: Metadata = {
  title: "Contact | Zroky",
  description: "Contact the Zroky team.",
};

export default function ContactPage() {
  return (
    <PublicInfoPage
      eyebrow="Contact"
      title="Contact Zroky"
      summary="Talk to the Zroky team about reliability workflows, production rollout, billing, or security."
    >
      <h2>General</h2>
      <p>
        For product and workspace questions, email <a href="mailto:contact@zroky.com">contact@zroky.com</a>.
      </p>
      <h2>Security</h2>
      <p>
        For security reports, email <a href="mailto:security@zroky.com">security@zroky.com</a>.
      </p>
      <h2>Support context</h2>
      <p>
        Include your workspace name, affected route, and a short description of the failure or rollout blocker.
      </p>
    </PublicInfoPage>
  );
}
