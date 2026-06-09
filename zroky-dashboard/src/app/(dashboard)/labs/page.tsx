import Link from "next/link";
import { Activity, Bot, FlaskConical } from "lucide-react";

const LABS = [
  {
    href: "/labs/agents",
    title: "Agent Console",
    description: "Reliability, cost, replay readiness, and blast radius across monitored agents.",
    Icon: Bot,
  },
  {
    href: "/labs/drift",
    title: "Provider Drift",
    description: "Provider, model, and judge behavior drift signals kept outside the primary workflow.",
    Icon: Activity,
  },
];

export default function LabsPage() {
  return (
    <div className="page-content labs-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="labs-eyebrow">
              <FlaskConical size={14} aria-hidden="true" />
              Labs
            </span>
            <h1>Labs</h1>
            <p>Experimental and secondary analysis surfaces live here until they earn primary navigation.</p>
          </div>
        </div>
      </section>

      <section className="labs-grid">
        {LABS.map(({ href, title, description, Icon }) => (
          <Link key={href} href={href} className="panel labs-card">
            <span className="labs-icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            <div>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
