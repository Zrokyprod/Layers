import { Link } from 'react-router-dom';
import { Github, Linkedin, Twitter } from 'lucide-react';

const COLS = [
  {
    title: 'Control plane',
    links: [
      { label: 'Protected actions', href: '/#product' },
      { label: 'Receipts', href: '/#receipts' },
      { label: 'Agent categories', href: '/#agents' },
      { label: 'Pricing', href: '/#pricing' },
    ],
  },
  {
    title: 'Developers',
    links: [
      { label: 'Docs', href: '/docs' },
      { label: 'Quickstart', href: '/#quickstart' },
      { label: 'Agent setup', href: '/#agents' },
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
    <footer className="relative z-10 w-full border-t border-[#d8dbd2] bg-[#eef0eb] text-[#20231f]">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-10 px-6 py-16 md:grid-cols-5">
        <div className="col-span-2">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/zroky.png" alt="Zroky" className="h-7 w-7 rounded-[8px] object-contain" />
            <span className="text-[15px] font-semibold tracking-[-0.02em] text-[#20231f]">Zroky</span>
          </Link>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-[#5b615a]">
            Agent reliability control plane for high-risk actions, approval gates, system-of-record verification, and signed receipts.
          </p>
          <div className="mt-5 flex items-center gap-3 text-[#8b9288]">
            <a href="https://github.com/zroky" className="transition hover:text-[#4f5a52]" aria-label="Zroky on GitHub">
              <Github size={18} />
            </a>
            <a href="https://x.com/zroky" className="transition hover:text-[#4f5a52]" aria-label="Zroky on X">
              <Twitter size={18} />
            </a>
            <a href="https://linkedin.com/company/zroky" className="transition hover:text-[#4f5a52]" aria-label="Zroky on LinkedIn">
              <Linkedin size={18} />
            </a>
          </div>
        </div>
        {COLS.map((col) => (
          <div key={col.title}>
            <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8b9288]">{col.title}</h4>
            <ul className="mt-4 space-y-2.5">
              {col.links.map((link) => (
                <li key={link.label}>
                  <a href={link.href} className="text-sm text-[#5b615a] transition hover:text-[#4f5a52]">
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-[#d8dbd2]">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-6 text-xs text-[#8b9288] sm:flex-row">
          <p>Copyright {new Date().getFullYear()} Zroky. Built for production AI agents.</p>
          <p className="font-mono">AI explains. Policy decides. System of record proves.</p>
        </div>
      </div>
    </footer>
  );
}
