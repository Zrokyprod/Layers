import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, RefreshCw } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { VerifyScene } from '../../components/auth/AuthScenes';
import { AUTH_LINK, AUTH_PRIMARY_BUTTON, AUTH_SECONDARY_BUTTON } from './authStyles';

const nextSteps = [
  { step: '01', title: 'Create project access', desc: 'Generate a Zroky project key for capture.' },
  { step: '02', title: 'Capture one agent flow', desc: 'Use SDK or Gateway and confirm the first trace appears.' },
  { step: '03', title: 'Replay only when needed', desc: 'Connect a provider key when verified replay is ready.' },
];

export default function VerifyEmailPage() {
  return (
    <AuthLayout
      scene={<VerifyScene />}
      tagline="Identity confirmed. Your agent workspace is ready to capture production failures."
      caption="Start with capture, then add replay proof and CI gates when your first incident needs protection."
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
        className="flex w-fit items-center gap-2 rounded-lg border border-verified/35 bg-verified/10 px-4 py-2"
      >
        <span className="h-2 w-2 rounded-full bg-verified" />
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-verified">Email verified</span>
      </motion.div>

      <div className="mt-5">
        <h1 className="text-2xl font-semibold text-white">Workspace is ready</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">
          Your email has been verified. Follow the docs path to capture the first protected agent flow.
        </p>
      </div>

      <div className="mt-8 space-y-3">
        {nextSteps.map(({ step, title, desc }) => (
          <motion.div
            key={step}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.32, delay: Number(step) * 0.08 }}
            className="flex items-center gap-4 rounded-lg border border-white/[0.12] bg-white/[0.035] p-4"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.12] bg-white/[0.06] font-mono text-xs font-semibold text-white">
              {step}
            </div>
            <div>
              <p className="text-sm font-semibold text-white">{title}</p>
              <p className="text-xs font-semibold leading-5 text-white/58">{desc}</p>
            </div>
          </motion.div>
        ))}
      </div>

      <motion.a
        href="/docs/quickstart"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.42 }}
        className={`mt-6 ${AUTH_PRIMARY_BUTTON}`}
      >
        Open quickstart guide
        <ArrowRight className="h-4 w-4" />
      </motion.a>

      <button type="button" className={`mt-3 ${AUTH_SECONDARY_BUTTON}`}>
        <RefreshCw className="h-4 w-4" />
        Resend verification email
      </button>

      <p className="mt-6 text-center text-xs font-semibold text-white/58">
        Already have an account?{' '}
        <Link to="/auth/login" className={AUTH_LINK}>
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
