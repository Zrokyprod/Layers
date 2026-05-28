import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Github, Menu, X } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  { label: 'Features', to: '/features' },
  { label: 'Changelog', to: '/changelog' },
  { label: 'Docs', to: '/docs' },
  { label: 'Pricing', to: '/pricing' },
];

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 18);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      <motion.header
        initial={{ y: -18, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        className="fixed left-0 right-0 top-10 z-50 px-3 pt-3 sm:px-4 lg:px-6"
      >
        <div
          className={`mx-auto flex max-w-[92rem] items-center justify-between rounded-full transition-all duration-300 ${
            scrolled
              ? 'border border-panel-border bg-white/92 px-4 py-2.5 shadow-premium backdrop-blur-2xl'
              : 'bg-white/60 px-2 py-2 backdrop-blur-xl'
          }`}
        >
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3 rounded-full px-2" aria-label="Zroky home">
            <span className="flex h-11 w-[148px] items-center">
              <img src="/zroky.logo.png" alt="Zroky" className="h-9 w-full object-contain" />
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden items-center gap-1 rounded-full border border-panel-border bg-white/80 p-1 text-sm font-extrabold text-secondary shadow-sm lg:flex">
            {navItems.map((item) => {
              const active = pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`inline-flex min-h-11 items-center rounded-full px-4 py-2 transition duration-200 focus:outline-none focus:ring-2 focus:ring-accent/35 ${
                    active
                      ? 'bg-primary text-white'
                      : 'hover:bg-canvas hover:text-primary'
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
            <a
              href="https://github.com/zroky-ai"
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-4 py-2 transition duration-200 hover:bg-canvas hover:text-primary"
            >
              <Github className="h-4 w-4" />
              <span>GitHub</span>
            </a>
          </nav>

          {/* Desktop CTAs */}
          <div className="hidden items-center gap-2 lg:flex">
            <a
              href="/auth/login"
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-panel-border bg-white px-4 py-2 text-sm font-extrabold text-primary shadow-sm transition duration-200 hover:border-accent/35 hover:bg-accent/10"
            >
              Login
            </a>
            <Link
              to="/pricing"
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-accent focus:outline-none focus:ring-2 focus:ring-accent/35"
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* Mobile menu button */}
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            className="grid h-11 w-11 place-items-center rounded-full border border-panel-border bg-white text-primary lg:hidden"
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </motion.header>

      {/* Mobile drawer */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="fixed inset-x-3 top-[5.5rem] z-40 overflow-hidden rounded-3xl border border-panel-border bg-white shadow-premium lg:hidden"
        >
          <nav className="flex flex-col divide-y divide-panel-border p-2">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="flex min-h-12 items-center rounded-2xl px-4 text-sm font-extrabold text-primary transition hover:bg-canvas"
              >
                {item.label}
              </Link>
            ))}
            <a
              href="https://github.com/zroky-ai"
              target="_blank"
              rel="noreferrer"
              className="flex min-h-12 items-center gap-2 rounded-2xl px-4 text-sm font-extrabold text-primary transition hover:bg-canvas"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </nav>
          <div className="flex gap-2 border-t border-panel-border p-3">
            <a href="/auth/login" className="flex-1 inline-flex min-h-11 items-center justify-center rounded-full border border-panel-border text-sm font-extrabold text-primary transition hover:bg-canvas">
              Login
            </a>
            <Link to="/pricing" className="flex-1 inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-primary text-sm font-extrabold text-white transition hover:bg-accent">
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </motion.div>
      )}
    </>
  );
}
