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
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';
import CheckEmailPage from './pages/auth/CheckEmailPage';
import ResetPasswordPage from './pages/auth/ResetPasswordPage';
import VerifyEmailPage from './pages/auth/VerifyEmailPage';

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

const AUTH_PATHS = ['/auth/'];

function App() {
  const location = useLocation();
  const isAuth = AUTH_PATHS.some((p) => location.pathname.startsWith(p));

  return (
    <div className="relative min-h-screen overflow-x-clip bg-ink">
      {!isAuth && <div className="pointer-events-none fixed inset-0 z-0 grid-bg opacity-60" />}
      <ScrollToTop />
      {!isAuth && <Nav />}
      <main className={isAuth ? '' : 'relative z-10 flex w-full flex-col items-center overflow-x-hidden'}>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<PageFade><HomePage /></PageFade>} />
            <Route path="/pricing" element={<PageFade><PricingPage /></PageFade>} />
            <Route path="/changelog" element={<PageFade><ChangelogPage /></PageFade>} />
            <Route path="/docs" element={<PageFade><DocsPage /></PageFade>} />
            <Route path="/auth/login" element={<PageFade><LoginPage /></PageFade>} />
            <Route path="/auth/register" element={<PageFade><RegisterPage /></PageFade>} />
            <Route path="/auth/forgot-password" element={<PageFade><ForgotPasswordPage /></PageFade>} />
            <Route path="/auth/check-email" element={<PageFade><CheckEmailPage /></PageFade>} />
            <Route path="/auth/reset-password" element={<PageFade><ResetPasswordPage /></PageFade>} />
            <Route path="/auth/verify-email" element={<PageFade><VerifyEmailPage /></PageFade>} />
          </Routes>
        </AnimatePresence>
      </main>
      {!isAuth && <Footer />}
    </div>
  );
}

export default App;
