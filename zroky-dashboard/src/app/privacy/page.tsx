import type { Metadata } from "next";

import { PublicInfoPage } from "@/components/public-info-page";

export const metadata: Metadata = {
  title: "Privacy | Zroky",
  description: "How Zroky handles reliability telemetry, account data, and customer controls.",
};

export default function PrivacyPage() {
  return (
    <PublicInfoPage
      eyebrow="Privacy"
      title="Privacy at Zroky"
      summary="Zroky captures the operational evidence teams need to debug and protect AI-agent runs."
    >
      <h2>Data we process</h2>
      <p>
        Zroky stores account details, project metadata, API-key metadata, captured trace evidence, replay records,
        and billing usage needed to run the product.
      </p>
      <h2>Customer controls</h2>
      <p>
        Organizations can rotate or revoke project keys, separate provider keys from capture keys, and control which
        production evidence is promoted into replay fixtures and regression contracts.
      </p>
      <h2>Operational use</h2>
      <p>
        Reliability data is used to diagnose failures, group repeated issues, meter usage, and keep the service
        secure and observable.
      </p>
    </PublicInfoPage>
  );
}
