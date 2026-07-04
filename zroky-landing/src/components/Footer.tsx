import { Link } from 'react-router-dom';
import { Github, Linkedin, Twitter } from 'lucide-react';

const COLS = [
  {
    title: 'Control plane',
    links: [
      { label: 'Control loop', href: '/#architecture' },
      { label: 'Sequence risk', href: '/#sequence-risk' },
      { label: 'Receipts', href: '/#receipts' },
      { label: 'Pricing', href: '/pricing' },
    ],
  },
  {
    title: 'Developers',
    links: [
      { label: 'Docs', href: '/docs' },
      { label: 'Quickstart', href: '/#quickstart' },
      { label: 'Agent setup', href: '/docs' },
      { label: 'Changelog', href: '/changelog' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'Enterprise readiness', href: '/#trust' },
      { label: 'Privacy', href: '/privacy' },
      { label: 'Terms', href: '/terms' },
      { label: 'Contact', href: 'mailto:hello@zroky.com' },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="relative z-10 w-full border-t border-[#d8dbd2] bg-[#eef0eb] text-[#20231f]">
      <div className="mx-auto grid max-w-[1260px] grid-cols-1 gap-10 px-6 py-16 sm:grid-cols-2 md:grid-cols-5">
        <div className="sm:col-span-2">
          <Link to="/" className="flex min-w-0 items-center">
            <img
              src="/zroky-brand.png"
              alt="Zroky"
              className="h-8 w-[118px] object-contain object-left"
            />
          </Link>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-[#5b615a]">
            AI agent action control plane for policy gates, scoped execution, source-of-record verification, and signed receipts.
          </p>
          <div className="mt-5 flex items-center gap-3 text-[#8b9288]">
            <a href="https://github.com/zroky-ai" className="transition hover:text-[#4f5a52]" aria-label="Zroky on GitHub">
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
        <div className="mx-auto flex max-w-[1260px] flex-col items-center justify-between gap-3 px-6 py-6 text-xs text-[#8b9288] sm:flex-row">
          <p>Copyright {new Date().getFullYear()} Zroky. Built for production AI agents.</p>
          <p className="font-mono">Policy decides. Systems prove. Receipts travel.</p>
        </div>
      </div>
    </footer>
  );
}
