import type { Metadata } from "next";

import { PublicInfoPage } from "@/components/public-info-page";

export const metadata: Metadata = {
  title: "Security | Zroky",
  description: "Security practices for Zroky's AI-agent reliability platform.",
};

export default function SecurityPage() {
  return (
    <PublicInfoPage
      eyebrow="Security"
      title="Security model"
      summary="Zroky separates capture credentials, provider credentials, user sessions, and project access controls."
    >
      <h2>Credential separation</h2>
      <p>
        Project keys are used for capture and ingest. Provider keys are separate and are only needed when verified
        replay runs against a model provider.
      </p>
      <h2>Access control</h2>
      <p>
        Dashboard access uses workspace membership, session cookies, project-scoped routing, and guarded destructive
        actions.
      </p>
      <h2>Report a concern</h2>
      <p>
        Send security reports to <a href="mailto:security@zroky.com">security@zroky.com</a>.
      </p>
    </PublicInfoPage>
  );
}
