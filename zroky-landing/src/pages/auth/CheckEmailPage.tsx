import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, RefreshCw } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { CheckEmailScene } from '../../components/auth/AuthScenes';
import { AUTH_LINK, AUTH_SECONDARY_BUTTON } from './authStyles';

const steps = [
  'Open the email from Zroky.',
  'Use the one-time link before it expires.',
  'Return to the workspace and continue capture or replay setup.',
];

export default function CheckEmailPage() {
  return (
    <AuthLayout
      scene={<CheckEmailScene />}
      tagline="Email verification protects workspace access without slowing down capture setup."
      caption="Your agent evidence, replay runs, and provider key settings stay isolated from email recovery."
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="mx-auto flex h-16 w-16 items-center justify-center rounded-lg border border-white/[0.12] bg-white/[0.04]"
      >
        <Mail className="h-7 w-7 text-white" />
      </motion.div>

      <div className="mt-6 text-center">
        <h1 className="text-2xl font-semibold text-white">Check your inbox</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">
          We sent a secure link to <span className="text-white">you@company.com</span>. Open it to continue.
        </p>
      </div>

      <div className="mt-8 space-y-3">
        {steps.map((step, index) => (
          <div key={step} className="flex items-center gap-3 rounded-lg border border-white/[0.12] bg-white/[0.035] p-4">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.12] bg-white/[0.06] font-mono text-xs font-semibold text-white">
              {index + 1}
            </div>
            <p className="text-xs font-semibold leading-5 text-white/68">{step}</p>
          </div>
        ))}
      </div>

      <button type="button" className={`mt-6 ${AUTH_SECONDARY_BUTTON}`}>
        <RefreshCw className="h-4 w-4" />
        Resend email
      </button>

      <p className="mt-6 text-center text-xs font-semibold text-white/58">
        Wrong address?{' '}
        <Link to="/auth/forgot-password" className={AUTH_LINK}>
          Try again
        </Link>
        {' / '}
        <Link to="/auth/login" className={AUTH_LINK}>
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
