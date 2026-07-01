import LegalPage from './LegalPage';

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      updated="February 2025"
      intro="These Terms of Service govern your access to and use of Zroky, the agent reliability control plane, including the website, dashboard, APIs, and SDKs. By using Zroky you agree to these terms."
      sections={[
        {
          heading: 'Use of the service',
          body: (
            <p>
              You may use Zroky to gate, verify, and produce evidence for your own AI agent actions. You are responsible
              for the agents, policies, and connectors you configure and for complying with applicable laws.
            </p>
          ),
        },
        {
          heading: 'Accounts and access',
          body: (
            <p>
              You must provide accurate account information and keep your API keys and credentials secure. You are
              responsible for activity under your account and project keys.
            </p>
          ),
        },
        {
          heading: 'Plans and billing',
          body: (
            <p>
              Paid plans are billed according to the pricing in effect at purchase. Usage limits and overage terms are
              described on the pricing page. Fees are non-refundable except where required by law.
            </p>
          ),
        },
        {
          heading: 'Acceptable use',
          body: (
            <p>
              You may not use Zroky to bypass security controls, process unlawful content, or attempt to disrupt the
              service. We may suspend access for violations that create risk to the platform or other customers.
            </p>
          ),
        },
        {
          heading: 'Disclaimers and liability',
          body: (
            <p>
              Zroky is provided on an "as is" basis. To the maximum extent permitted by law, Zroky is not liable for
              indirect or consequential damages. Nothing in these terms limits liability that cannot be limited by law.
            </p>
          ),
        },
        {
          heading: 'Changes to these terms',
          body: (
            <p>
              We may update these terms as the service evolves. Continued use after changes take effect constitutes
              acceptance of the updated terms.
            </p>
          ),
        },
      ]}
    />
  );
}
