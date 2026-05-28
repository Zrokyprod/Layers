import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, CheckCircle2 } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { ResetScene } from '../../components/auth/AuthScenes';

const INPUT = 'block w-full rounded-xl border border-panel-border bg-white px-4 py-3 text-sm font-bold text-primary placeholder:font-normal placeholder:text-tertiary transition duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';
const LABEL = 'mb-1.5 block text-xs font-extrabold uppercase tracking-[0.12em] text-tertiary';

const requirements = [
  'At least 12 characters',
  'One uppercase letter',
  'One number or symbol',
];

export default function ResetPasswordPage() {
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/auth/login');
  };

  return (
    <AuthLayout
      scene={<ResetScene />}
      tagline="Access restored. Your agent evidence trail picks up exactly where it left off."
      caption="All your issues, replays, and goldens are safe and waiting."
    >
      <div>
        <h1 className="text-2xl font-black text-primary">Set new password</h1>
        <p className="mt-1.5 text-sm font-bold text-secondary">
          Choose a strong password for your Zroky workspace.
        </p>
      </div>

      <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={LABEL}>New password</label>
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              placeholder="Min. 12 characters"
              autoComplete="new-password"
              className={`${INPUT} pr-12`}
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-tertiary transition hover:text-primary"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className={LABEL}>Confirm password</label>
          <div className="relative">
            <input
              type={showConfirm ? 'text' : 'password'}
              placeholder="Repeat password"
              autoComplete="new-password"
              className={`${INPUT} pr-12`}
            />
            <button
              type="button"
              onClick={() => setShowConfirm((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-tertiary transition hover:text-primary"
            >
              {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-panel-border bg-white p-4">
          <p className="mb-3 text-xs font-extrabold uppercase tracking-[0.12em] text-tertiary">Requirements</p>
          <div className="space-y-2">
            {requirements.map((req) => (
              <div key={req} className="flex items-center gap-2.5 text-xs font-bold text-secondary">
                <CheckCircle2 className="h-3.5 w-3.5 text-tertiary" />
                {req}
              </div>
            ))}
          </div>
        </div>

        <motion.button
          type="submit"
          whileTap={{ scale: 0.98 }}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-primary py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          Reset password
          <ArrowRight className="h-4 w-4" />
        </motion.button>
      </form>

      <p className="mt-6 text-center text-xs font-bold text-secondary">
        Remembered it?{' '}
        <Link to="/auth/login" className="font-extrabold text-accent hover:underline">
          Sign in instead
        </Link>
      </p>
    </AuthLayout>
  );
}
