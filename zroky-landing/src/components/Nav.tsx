import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Menu, X, Star, ArrowUpRight } from 'lucide-react';

const LINKS = [
  { label: 'Product', to: '/#product' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Docs', to: '/docs' },
  { label: 'Changelog', to: '/changelog' },
];

const DASHBOARD_URL = 'https://app.zroky.com';
const GITHUB_URL = 'https://github.com/zroky/zroky-watch';

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => { setOpen(false); }, [location.pathname]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-3">
      <motion.nav
        initial={{ y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={`flex w-full max-w-6xl items-center justify-between rounded-2xl border px-4 py-2.5 transition-all duration-300 ${
          scrolled
            ? 'border-line-strong bg-ink/80 backdrop-blur-xl shadow-card'
            : 'border-line bg-ink/40 backdrop-blur-md'
        }`}
      >
        <Link to="/" className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-ink font-black text-sm">Z</div>
          <span className="text-[15px] font-bold tracking-tight">Zroky</span>
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.to}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-secondary transition hover:text-primary"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          <a href={GITHUB_URL} className="btn-ghost !px-3 !py-2" aria-label="Star zroky-watch on GitHub">
            <Star size={14} /> <span className="text-xs">zroky-watch</span>
          </a>
          <a href={`${DASHBOARD_URL}/auth/login`} className="rounded-full px-3 py-2 text-sm font-semibold text-secondary transition hover:text-primary">
            Sign in
          </a>
          <a href={`${DASHBOARD_URL}/auth/register`} className="btn-primary">
            Start free <ArrowUpRight size={15} />
          </a>
        </div>

        <button className="md:hidden p-2 text-primary" onClick={() => setOpen((v) => !v)} aria-label="Menu">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </motion.nav>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="absolute inset-x-4 top-[68px] z-50 rounded-2xl border border-line-strong bg-ink/95 p-4 backdrop-blur-xl md:hidden"
          >
            <div className="flex flex-col gap-1">
              {LINKS.map((l) => (
                <a key={l.label} href={l.to} className="rounded-lg px-3 py-2.5 text-sm font-medium text-secondary hover:bg-white/5 hover:text-primary">
                  {l.label}
                </a>
              ))}
            </div>
            <div className="mt-3 flex flex-col gap-2 border-t border-line pt-3">
              <a href={GITHUB_URL} className="btn-ghost w-full"><Star size={14} /> Star zroky-watch</a>
              <a href={`${DASHBOARD_URL}/auth/register`} className="btn-primary w-full">Start free <ArrowUpRight size={15} /></a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
