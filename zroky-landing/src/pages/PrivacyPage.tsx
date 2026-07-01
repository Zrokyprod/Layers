import LegalPage from './LegalPage';

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      updated="February 2025"
      intro="This Privacy Policy explains how Zroky collects, uses, and protects information when you use the Zroky agent reliability control plane, our website, dashboard, SDKs, and related services."
      sections={[
        {
          heading: 'Information we collect',
          body: (
            <>
              <p>
                Account information you provide (name, work email, organization), and configuration data such as agent
                profiles, policies, and connector settings.
              </p>
              <p>
                Operational metadata required to evaluate and prove agent actions: policy decisions, approval events,
                execution attempts, verification results, and signed receipts. We do not require your model-provider keys
                to run verified actions.
              </p>
              <p>Standard technical data (IP address, browser type, and usage logs) for security and reliability.</p>
            </>
          ),
        },
        {
          heading: 'How we use information',
          body: (
            <p>
              To operate the control plane, evaluate high-risk actions, generate evidence and receipts, provide support,
              secure the service, meet legal obligations, and improve reliability. We do not sell personal information.
            </p>
          ),
        },
        {
          heading: 'Data retention',
          body: (
            <p>
              Evidence and receipts are retained according to your plan's retention window. You can request deletion of
              your account data subject to legal and audit requirements.
            </p>
          ),
        },
        {
          heading: 'Security',
          body: (
            <p>
              We apply encryption in transit, scoped credentials, isolated execution for agent actions, and access
              controls. Secrets such as provider keys are stored in an encrypted vault and never returned to clients.
            </p>
          ),
        },
        {
          heading: 'Your rights',
          body: (
            <p>
              Depending on your jurisdiction, you may have rights to access, correct, export, or delete your personal
              data. Contact us to exercise these rights.
            </p>
          ),
        },
        {
          heading: 'Changes to this policy',
          body: (
            <p>
              We may update this policy as the product evolves. Material changes will be reflected by the "last updated"
              date above.
            </p>
          ),
        },
      ]}
    />
  );
}
