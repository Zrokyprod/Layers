import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, RefreshCw } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { CheckEmailScene } from '../../components/auth/AuthScenes';

export default function CheckEmailPage() {
  return (
    <AuthLayout
      scene={<CheckEmailScene />}
      tagline="Encrypted in transit. Your access credentials never touch our logs."
      caption="Every reset token is one-time-use and expires in 15 minutes."
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-panel-border bg-white shadow-sm"
      >
        <Mail className="h-7 w-7 text-accent" />
      </motion.div>

      <div className="mt-6">
        <h1 className="text-2xl font-black text-primary">Check your inbox</h1>
        <p className="mt-1.5 text-sm font-bold text-secondary">
          We sent a secure link to{' '}
          <span className="font-extrabold text-primary">you@company.com</span>.
          Open it to continue.
        </p>
      </div>

      <div className="mt-8 space-y-3">
        <div className="flex items-center gap-3 rounded-2xl border border-panel-border bg-white p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-canvas font-mono text-xs font-black text-accent">
            1
          </div>
          <p className="text-xs font-bold leading-5 text-secondary">
            Open the email from <span className="font-extrabold text-primary">noreply@zroky.ai</span>
          </p>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-panel-border bg-white p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-canvas font-mono text-xs font-black text-accent">
            2
          </div>
          <p className="text-xs font-bold leading-5 text-secondary">
            Click <span className="font-extrabold text-primary">Continue to Zroky</span> — link expires in 15 min
          </p>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-panel-border bg-white p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-canvas font-mono text-xs font-black text-accent">
            3
          </div>
          <p className="text-xs font-bold leading-5 text-secondary">
            Set your new password and you're back in your workspace
          </p>
        </div>
      </div>

      <button
        type="button"
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-full border border-panel-border bg-white py-3 text-sm font-extrabold text-primary transition duration-200 hover:bg-canvas hover:border-accent/30"
      >
        <RefreshCw className="h-4 w-4" />
        Resend email
      </button>

      <p className="mt-6 text-center text-xs font-bold text-secondary">
        Wrong address?{' '}
        <Link to="/auth/forgot-password" className="font-extrabold text-accent hover:underline">
          Try again
        </Link>
        {' · '}
        <Link to="/auth/login" className="font-extrabold text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
