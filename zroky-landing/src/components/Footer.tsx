import { Github, Twitter } from 'lucide-react';
import { Link } from 'react-router-dom';

const cols = [
  {
    heading: 'Product',
    links: [
      { label: 'Features', to: '/features' },
      { label: 'Pricing', to: '/pricing' },
      { label: 'Changelog', to: '/changelog' },
      { label: 'Docs', to: '/docs' },
    ],
  },
  {
    heading: 'Open Source',
    links: [
      { label: 'zroky-sdk', href: 'https://github.com/zroky-ai/zroky-sdk' },
      { label: 'zroky-sdk-js', href: 'https://github.com/zroky-ai/zroky-sdk-js' },
      { label: 'zroky-gateway', href: 'https://github.com/zroky-ai/zroky-gateway' },
      { label: 'zroky-replay-worker', href: 'https://github.com/zroky-ai/zroky-replay-worker' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About', href: '#' },
      { label: 'Blog', href: '#' },
      { label: 'Careers', href: '#' },
      { label: 'Contact', href: 'mailto:hello@zroky.ai' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '#' },
      { label: 'Terms of Service', href: '#' },
      { label: 'FSL License', href: 'https://github.com/zroky-ai' },
      { label: 'Security', href: 'mailto:security@zroky.ai' },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="relative z-10 bg-primary pt-16 pb-10">
      <div className="mx-auto w-full max-w-[92rem] px-4 sm:px-5 lg:px-8">

        {/* Top: logo + tagline + socials */}
        <div className="mb-12 flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex h-10 w-[148px] items-center">
              <img src="/zroky.logo.png" alt="Zroky" className="h-8 w-full object-contain brightness-0 invert" />
            </div>
            <p className="mt-4 max-w-xs text-sm leading-7 text-slate-400">
              Production reliability for AI agents. Capture, diagnose, replay, and gate.
            </p>
            <div className="mt-5 flex items-center gap-2">
              <a
                href="https://github.com/zroky-ai"
                target="_blank"
                rel="noreferrer"
                className="grid h-9 w-9 place-items-center rounded-full border border-white/15 text-slate-400 transition hover:border-white/30 hover:text-white"
                aria-label="GitHub"
              >
                <Github className="h-4 w-4" />
              </a>
              <a
                href="https://x.com/zrokyai"
                target="_blank"
                rel="noreferrer"
                className="grid h-9 w-9 place-items-center rounded-full border border-white/15 text-slate-400 transition hover:border-white/30 hover:text-white"
                aria-label="Twitter / X"
              >
                <Twitter className="h-4 w-4" />
              </a>
              <a
                href="https://linkedin.com/company/zroky-ai"
                target="_blank"
                rel="noreferrer"
                className="grid h-9 w-9 place-items-center rounded-full border border-white/15 text-slate-400 transition hover:border-white/30 hover:text-white"
                aria-label="LinkedIn"
              >
                <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
              </a>
              <a
                href="https://instagram.com/zroky.ai"
                target="_blank"
                rel="noreferrer"
                className="grid h-9 w-9 place-items-center rounded-full border border-white/15 text-slate-400 transition hover:border-white/30 hover:text-white"
                aria-label="Instagram"
              >
                <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                  <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/>
                </svg>
              </a>
            </div>
          </div>

          {/* Link columns */}
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            {cols.map((col) => (
              <div key={col.heading}>
                <div className="mb-4 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                  {col.heading}
                </div>
                <div className="flex flex-col gap-2.5">
                  {col.links.map((link) => (
                    'to' in link ? (
                      <Link
                        key={link.label}
                        to={(link as { label: string; to: string }).to}
                        className="text-sm font-bold text-slate-400 transition hover:text-white"
                      >
                        {link.label}
                      </Link>
                    ) : (
                      <a
                        key={link.label}
                        href={(link as { label: string; href: string }).href}
                        target={(link as { label: string; href: string }).href.startsWith('http') ? '_blank' : undefined}
                        rel={(link as { label: string; href: string }).href.startsWith('http') ? 'noreferrer' : undefined}
                        className="text-sm font-bold text-slate-400 transition hover:text-white"
                      >
                        {link.label}
                      </a>
                    )
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col gap-3 border-t border-white/10 pt-8 text-xs font-bold text-slate-600 md:flex-row md:items-center md:justify-between">
          <span>© {new Date().getFullYear()} Zroky AI, Inc. All rights reserved.</span>
          <span>Licensed under FSL-1.1-MIT · Open source data plane</span>
        </div>

      </div>
    </footer>
  );
}
