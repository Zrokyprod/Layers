import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, CheckCircle2, Eye, EyeOff } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { ResetScene } from '../../components/auth/AuthScenes';
import { AUTH_INPUT, AUTH_LABEL, AUTH_LINK, AUTH_NOTE, AUTH_PRIMARY_BUTTON } from './authStyles';

const requirements = ['At least 12 characters', 'One uppercase letter', 'One number or symbol'];

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
      caption="Issues, replays, Goldens, and CI gates stay intact while workspace access is recovered."
    >
      <div>
        <h1 className="text-2xl font-semibold text-white">Set a new password</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">Choose a strong password for your Zroky workspace.</p>
      </div>

      <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={AUTH_LABEL}>New password</label>
          <div className="relative">
            <input type={showPw ? 'text' : 'password'} placeholder="Min. 12 characters" autoComplete="new-password" className={`${AUTH_INPUT} pr-12`} />
            <button
              type="button"
              onClick={() => setShowPw((value) => !value)}
              className="absolute right-4 top-3.5 text-white/55 transition hover:text-white"
              aria-label={showPw ? 'Hide password' : 'Show password'}
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className={AUTH_LABEL}>Confirm password</label>
          <div className="relative">
            <input type={showConfirm ? 'text' : 'password'} placeholder="Repeat password" autoComplete="new-password" className={`${AUTH_INPUT} pr-12`} />
            <button
              type="button"
              onClick={() => setShowConfirm((value) => !value)}
              className="absolute right-4 top-3.5 text-white/55 transition hover:text-white"
              aria-label={showConfirm ? 'Hide password confirmation' : 'Show password confirmation'}
            >
              {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className={AUTH_NOTE}>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-white/70">Requirements</p>
          <div className="space-y-2">
            {requirements.map((requirement) => (
              <div key={requirement} className="flex items-center gap-2.5 text-xs font-semibold text-white/64">
                <CheckCircle2 className="h-3.5 w-3.5 text-white/46" />
                {requirement}
              </div>
            ))}
          </div>
        </div>

        <motion.button type="submit" whileTap={{ scale: 0.98 }} className={AUTH_PRIMARY_BUTTON}>
          Reset password
          <ArrowRight className="h-4 w-4" />
        </motion.button>
      </form>

      <p className="mt-6 text-center text-xs font-semibold text-white/58">
        Remembered it?{' '}
        <Link to="/auth/login" className={AUTH_LINK}>
          Sign in instead
        </Link>
      </p>
    </AuthLayout>
  );
}
