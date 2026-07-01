import { Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { ReactNode } from 'react';
import Nav from './components/Nav';
import Footer from './components/Footer';
import HomePage from './pages/HomePage';
import PricingPage from './pages/PricingPage';
import ChangelogPage from './pages/ChangelogPage';
import DocsPage from './pages/DocsPage';
import { buildDashboardAuthUrl, isDashboardAuthAlias } from './lib/links';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

function PageFade({ children }: { children: ReactNode }) {
  return (
    <motion.div
      className="w-full"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

function DashboardAuthRedirect() {
  const location = useLocation();
  const targetUrl = buildDashboardAuthUrl(location.pathname, location.search);

  useEffect(() => {
    window.location.replace(targetUrl);
  }, [targetUrl]);

  return (
    <div className="grid min-h-screen place-items-center bg-white px-6 text-center">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[#8a8aa3]">Zroky app</p>
        <h1 className="mt-3 text-2xl font-semibold text-[#0b0b14]">Redirecting to secure auth...</h1>
      </div>
    </div>
  );
}

function App() {
  const location = useLocation();
  const isAuthRedirect = isDashboardAuthAlias(location.pathname);

  return (
    <div className="relative min-h-screen overflow-x-clip bg-white">
      <ScrollToTop />
      {!isAuthRedirect && <Nav />}
      <main className={isAuthRedirect ? '' : 'relative z-10 flex w-full flex-col items-center overflow-x-hidden'}>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<PageFade><HomePage /></PageFade>} />
            <Route path="/pricing" element={<PageFade><PricingPage /></PageFade>} />
            <Route path="/changelog" element={<PageFade><ChangelogPage /></PageFade>} />
            <Route path="/docs" element={<PageFade><DocsPage /></PageFade>} />
            <Route path="/auth/*" element={<DashboardAuthRedirect />} />
            <Route path="/login" element={<DashboardAuthRedirect />} />
            <Route path="/signup" element={<DashboardAuthRedirect />} />
            <Route path="/forgot-password" element={<DashboardAuthRedirect />} />
            <Route path="/reset-password" element={<DashboardAuthRedirect />} />
            <Route path="/verify-email" element={<DashboardAuthRedirect />} />
          </Routes>
        </AnimatePresence>
      </main>
      {!isAuthRedirect && <Footer />}
    </div>
  );
}

export default App;
