import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { ForgotScene } from '../../components/auth/AuthScenes';

const INPUT = 'block w-full rounded-xl border border-panel-border bg-white px-4 py-3 text-sm font-bold text-primary placeholder:font-normal placeholder:text-tertiary transition duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';
const LABEL = 'mb-1.5 block text-xs font-extrabold uppercase tracking-[0.12em] text-tertiary';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/auth/check-email');
  };

  return (
    <AuthLayout
      scene={<ForgotScene />}
      tagline="Zero-trust by design. Your keys never leave your infrastructure."
      caption="Zroky captures behaviour, not secrets. Provider keys stay in your vault."
    >
      <Link
        to="/auth/login"
        className="inline-flex items-center gap-1.5 text-xs font-extrabold text-tertiary transition hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to sign in
      </Link>

      <div className="mt-6">
        <h1 className="text-2xl font-black text-primary">Forgot your password?</h1>
        <p className="mt-1.5 text-sm font-bold text-secondary">
          Enter your work email and we'll send a reset link — valid for 15 minutes.
        </p>
      </div>

      <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={LABEL}>Work email</label>
          <input type="email" placeholder="you@company.com" autoComplete="email" required className={INPUT} />
        </div>

        <motion.button
          type="submit"
          whileTap={{ scale: 0.98 }}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-primary py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          Send reset link
          <ArrowRight className="h-4 w-4" />
        </motion.button>
      </form>

      <div className="mt-8 rounded-2xl border border-panel-border bg-white p-4">
        <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-tertiary">Security note</p>
        <p className="mt-1.5 text-xs font-bold leading-5 text-secondary">
          If the email matches a Zroky account, the reset link will arrive within 60 seconds.
          Links expire after 15 minutes and can only be used once.
        </p>
      </div>

      <p className="mt-6 text-center text-xs font-bold text-secondary">
        Remembered it?{' '}
        <Link to="/auth/login" className="font-extrabold text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
