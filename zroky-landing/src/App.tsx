import { Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { AnimatePresence, motion, useMotionValue, useSpring } from 'framer-motion';
import type { ReactNode } from 'react';
import AnnouncementBar from './components/AnnouncementBar';
import Nav from './components/Nav';
import Footer from './components/Footer';
import HomePage from './pages/HomePage';
import FeaturesPage from './pages/FeaturesPage';
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
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

function CursorGlow() {
  const mx = useMotionValue(-400);
  const my = useMotionValue(-400);
  const x = useSpring(mx, { stiffness: 80, damping: 22 });
  const y = useSpring(my, { stiffness: 80, damping: 22 });
  useEffect(() => {
    const move = (e: MouseEvent) => { mx.set(e.clientX - 200); my.set(e.clientY - 200); };
    window.addEventListener('mousemove', move);
    return () => window.removeEventListener('mousemove', move);
  }, [mx, my]);
  return (
    <motion.div
      className="pointer-events-none fixed z-0 h-[400px] w-[400px] rounded-full"
      style={{ x, y, background: 'radial-gradient(circle, rgba(59,130,246,0.07) 0%, transparent 70%)' }}
    />
  );
}

const AUTH_PATHS = ['/auth/login', '/auth/register', '/auth/forgot-password', '/auth/check-email', '/auth/reset-password', '/auth/verify-email'];

function App() {
  const location = useLocation();
  const isAuth = AUTH_PATHS.some((p) => location.pathname.startsWith(p));

  return (
    <div className="relative min-h-screen overflow-x-clip selection:bg-accent selection:text-white">
      {!isAuth && <div className="pointer-events-none fixed inset-0 z-0 signal-grid opacity-35" />}
      {!isAuth && <CursorGlow />}
      <ScrollToTop />
      {!isAuth && <AnnouncementBar />}
      {!isAuth && <Nav />}
      <main className={`${isAuth ? '' : 'relative z-10 flex w-full flex-col items-center overflow-x-clip'}`}>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<PageFade><HomePage /></PageFade>} />
            <Route path="/features" element={<PageFade><FeaturesPage /></PageFade>} />
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
