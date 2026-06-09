import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { ForgotScene } from '../../components/auth/AuthScenes';
import { AUTH_INPUT, AUTH_LABEL, AUTH_LINK, AUTH_NOTE, AUTH_PRIMARY_BUTTON } from './authStyles';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/auth/check-email');
  };

  return (
    <AuthLayout
      scene={<ForgotScene />}
      tagline="Access recovery stays separate from agent evidence and provider credentials."
      caption="Reset the workspace login without exposing capture keys or provider keys."
    >
      <Link to="/auth/login" className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/58 transition hover:text-white">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to sign in
      </Link>

      <div className="mt-6">
        <h1 className="text-2xl font-semibold text-white">Reset workspace access</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">
          Enter your work email and we will send a one-time reset link.
        </p>
      </div>

      <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={AUTH_LABEL}>Work email</label>
          <input type="email" placeholder="you@company.com" autoComplete="email" required className={AUTH_INPUT} />
        </div>

        <motion.button type="submit" whileTap={{ scale: 0.98 }} className={AUTH_PRIMARY_BUTTON}>
          Send reset link
          <ArrowRight className="h-4 w-4" />
        </motion.button>
      </form>

      <div className={`mt-8 ${AUTH_NOTE}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/70">Security note</p>
        <p className="mt-1.5 text-xs font-semibold leading-5 text-white/62">
          If the email matches a Zroky account, the reset link will arrive shortly. Links expire and can only be used once.
        </p>
      </div>

      <p className="mt-6 text-center text-xs font-semibold text-white/58">
        Remembered it?{' '}
        <Link to="/auth/login" className={AUTH_LINK}>
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
