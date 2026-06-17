import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";

type PublicInfoPageProps = {
  eyebrow: string;
  title: string;
  summary: string;
  children: ReactNode;
};

export function PublicInfoPage({ eyebrow, title, summary, children }: PublicInfoPageProps) {
  return (
    <main className="public-info-page">
      <nav className="public-info-nav" aria-label="Public page navigation">
        <Link href="/" className="public-info-brand">
          <Image src="/logo.png" alt="Zroky" width={1550} height={509} priority />
        </Link>
        <div>
          <Link href="/login">Sign in</Link>
          <Link href="/signup" className="public-info-cta">Start workspace</Link>
        </div>
      </nav>
      <section className="public-info-hero">
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        <p>{summary}</p>
      </section>
      <section className="public-info-content">{children}</section>
    </main>
  );
}
