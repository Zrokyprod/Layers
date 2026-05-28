import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, RefreshCw } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { VerifyScene } from '../../components/auth/AuthScenes';

export default function VerifyEmailPage() {
  return (
    <AuthLayout
      scene={<VerifyScene />}
      tagline="Identity confirmed. Your agent workspace is ready to capture production failures."
      caption="You're now part of teams shipping reliable AI agents with confidence."
    >
      {/* Success badge */}
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5, type: 'spring', stiffness: 200 }}
        className="flex items-center gap-2 rounded-full border border-success/25 bg-success/8 px-4 py-2 w-fit"
      >
        <span className="h-2 w-2 rounded-full bg-success" />
        <span className="text-xs font-extrabold uppercase tracking-[0.12em] text-success">
          Email verified
        </span>
      </motion.div>

      <div className="mt-5">
        <h1 className="text-2xl font-black text-primary">You're all set!</h1>
        <p className="mt-1.5 text-sm font-bold text-secondary">
          Your email has been verified. Your Zroky workspace is ready.
        </p>
      </div>

      <div className="mt-8 space-y-3">
        {[
          { step: '01', title: 'Connect your agent', desc: 'Add the SDK decorator — 30 seconds.' },
          { step: '02', title: 'See your first capture', desc: 'Run your agent and watch issues appear.' },
          { step: '03', title: 'Trigger a replay', desc: 'Reproduce the failure with one click.' },
        ].map(({ step, title, desc }) => (
          <motion.div
            key={step}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: Number(step) * 0.1 }}
            className="flex items-center gap-4 rounded-2xl border border-panel-border bg-white p-4"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-panel-border bg-canvas font-mono text-xs font-black text-accent">
              {step}
            </div>
            <div>
              <p className="text-sm font-black text-primary">{title}</p>
              <p className="text-xs font-bold text-secondary">{desc}</p>
            </div>
          </motion.div>
        ))}
      </div>

      <motion.a
        href="/docs"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-primary py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/40"
      >
        Open quickstart guide
        <ArrowRight className="h-4 w-4" />
      </motion.a>

      <button
        type="button"
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-full border border-panel-border bg-white py-3 text-sm font-extrabold text-primary transition duration-200 hover:bg-canvas hover:border-accent/30"
      >
        <RefreshCw className="h-4 w-4" />
        Resend verification email
      </button>

      <p className="mt-6 text-center text-xs font-bold text-secondary">
        Already have an account?{' '}
        <Link to="/auth/login" className="font-extrabold text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
