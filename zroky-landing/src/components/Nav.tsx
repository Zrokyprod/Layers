import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Menu, X, ArrowUpRight, CalendarDays } from 'lucide-react';
import { DEMO_URL, SIGN_IN_URL, SIGN_UP_URL } from '../lib/links';

const LINKS = [
  { label: 'Connectors', to: '/#connectors' },
  { label: 'Agents', to: '/#agents' },
  { label: 'Receipts', to: '/#receipts' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Docs', to: '/docs' },
];

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

  useEffect(() => { setOpen(false); }, [location.hash, location.pathname]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-3">
      <motion.nav
        initial={{ y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={`flex w-full max-w-[1260px] items-center justify-between rounded-2xl border px-4 py-2.5 transition-all duration-300 ${
          scrolled
            ? 'border-[#d8dbd2] bg-[#fbfcf8]/84 shadow-[0_1px_2px_rgba(42,45,40,0.04),0_18px_40px_-28px_rgba(42,45,40,0.25)] backdrop-blur-xl'
            : 'border-[#d8dbd2]/60 bg-[#f7f8f4]/62 backdrop-blur-md'
        }`}
      >
        <Link to="/" className="flex min-w-0 items-center">
          <img
            src="/zroky-brand.png"
            alt="Zroky"
            className="h-8 w-[118px] object-contain object-left"
          />
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.to}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-[#5b615a] transition hover:text-[#20231f]"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          <a href={SIGN_IN_URL} className="rounded-full px-3 py-2 text-sm font-semibold text-[#5b615a] transition hover:text-[#20231f]">
            Sign in
          </a>
          <a
            href={DEMO_URL}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#3a747c,#2f5f66)] px-4 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_20px_-12px_rgba(47,95,102,0.58)] transition hover:-translate-y-px active:scale-[0.98]"
          >
            <CalendarDays size={15} /> Book a demo
          </a>
        </div>

        <button className="p-2 text-[#20231f] md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Menu">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </motion.nav>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="absolute inset-x-4 top-[68px] z-50 rounded-2xl border border-[#d8dbd2] bg-[#fbfcf8]/95 p-4 shadow-[0_18px_40px_-24px_rgba(42,45,40,0.25)] backdrop-blur-xl md:hidden"
          >
            <div className="flex flex-col gap-1">
              {LINKS.map((l) => (
                <a
                  key={l.label}
                  href={l.to}
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-3 py-2.5 text-sm font-medium text-[#5b615a] hover:bg-[#eef0eb] hover:text-[#20231f]"
                >
                  {l.label}
                </a>
              ))}
            </div>
            <div className="mt-3 flex flex-col gap-2 border-t border-[#d8dbd2] pt-3">
              <a
                href={SIGN_IN_URL}
                onClick={() => setOpen(false)}
                className="rounded-[10px] px-3 py-2.5 text-sm font-semibold text-[#5b615a] hover:text-[#20231f]"
              >
                Sign in
              </a>
              <a
                href={SIGN_UP_URL}
                onClick={() => setOpen(false)}
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#3a747c,#2f5f66)] px-4 text-sm font-semibold text-white"
              >
                Start free <ArrowUpRight size={15} />
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
