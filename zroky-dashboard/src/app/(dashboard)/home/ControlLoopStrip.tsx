"use client";

import Link from "next/link";

const LOOP_LINKS = [
  { label: "Agents", href: "/agents" },
  { label: "Policies", href: "/policies" },
  { label: "Approvals", href: "/approvals" },
  { label: "Outcomes", href: "/outcomes" },
  { label: "Evidence", href: "/evidence" },
  { label: "Connectors", href: "/connectors" },
] as const;

export function ControlLoopStrip() {
  return (
    <nav className="mc-loop-strip" aria-label="Control loop navigation">
      {LOOP_LINKS.map((item) => (
        <Link href={item.href} key={item.href}>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
