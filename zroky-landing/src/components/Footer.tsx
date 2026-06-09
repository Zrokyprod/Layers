import { Link } from 'react-router-dom';
import { Github, Twitter, Linkedin } from 'lucide-react';

const COLS = [
  {
    title: 'Product',
    links: [
      { label: 'Discover', href: '/#discover' },
      { label: 'Prove', href: '/#prove' },
      { label: 'Guard', href: '/#guard' },
      { label: 'Pricing', href: '/pricing' },
    ],
  },
  {
    title: 'Developers',
    links: [
      { label: 'Docs', href: '/docs' },
      { label: 'Quickstart', href: '/docs#quickstart' },
      { label: 'zroky-watch (OSS)', href: 'https://github.com/zroky/zroky-watch' },
      { label: 'Changelog', href: '/changelog' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'Security', href: '/#trust' },
      { label: 'Privacy', href: '/privacy' },
      { label: 'Terms', href: '/terms' },
      { label: 'Contact', href: 'mailto:hello@zroky.com' },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="relative z-10 mt-32 w-full border-t border-line bg-ink/60">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-10 px-6 py-16 md:grid-cols-5">
        <div className="col-span-2">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-ink font-black text-sm">Z</div>
            <span className="text-[15px] font-bold tracking-tight">Zroky</span>
          </Link>
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-tertiary">
            Find the AI agent failures you didn't know to test. Discover, prove, and guard production agents.
          </p>
          <div className="mt-5 flex items-center gap-3 text-tertiary">
            <a href="https://github.com/zroky" className="transition hover:text-primary"><Github size={18} /></a>
            <a href="https://x.com/zroky" className="transition hover:text-primary"><Twitter size={18} /></a>
            <a href="https://linkedin.com/company/zroky" className="transition hover:text-primary"><Linkedin size={18} /></a>
          </div>
        </div>
        {COLS.map((col) => (
          <div key={col.title}>
            <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-tertiary">{col.title}</h4>
            <ul className="mt-4 space-y-2.5">
              {col.links.map((l) => (
                <li key={l.label}>
                  <a href={l.href} className="text-sm text-secondary transition hover:text-primary">{l.label}</a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-6 text-xs text-tertiary sm:flex-row">
          <p>© {new Date().getFullYear()} Zroky. Built for production AI agents.</p>
          <p className="font-mono">AI Agent Failure Discovery &amp; Regression Guard</p>
        </div>
      </div>
    </footer>
  );
}
