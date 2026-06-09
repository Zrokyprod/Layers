import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { LoginScene } from '../../components/auth/AuthScenes';
import { getGithubOAuthUrl, loginWithPassword, redirectToDashboard } from '../../lib/auth-api';
import { AUTH_INPUT, AUTH_LABEL, AUTH_LINK, AUTH_PRIMARY_BUTTON, AUTH_SECONDARY_BUTTON } from './authStyles';

export default function LoginPage() {
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const email = emailRef.current?.value?.trim() ?? '';
    const password = passwordRef.current?.value ?? '';
    if (!email || !password) {
      setError('Please enter your email and password.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const tokens = await loginWithPassword(email, password);
      await redirectToDashboard(tokens);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid email or password.');
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      scene={<LoginScene />}
      tagline="Production AI agents, fully observed. Every failure has an evidence trail."
      caption="Sign in to inspect traces, replay fixes, promote Goldens, and protect releases."
    >
      <div>
        <h1 className="text-2xl font-semibold text-white">Welcome back</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">Sign in to your Zroky workspace.</p>
      </div>

      {error ? (
        <div className="mt-5 rounded-lg border border-blocked/35 bg-blocked/10 px-4 py-3 text-sm font-semibold text-blocked">
          {error}
        </div>
      ) : null}

      <form className="mt-5 space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={AUTH_LABEL}>Work email</label>
          <input ref={emailRef} type="email" placeholder="you@company.com" autoComplete="email" className={AUTH_INPUT} required />
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className={AUTH_LABEL}>Password</label>
            <Link to="/auth/forgot-password" className={`${AUTH_LINK} text-[11px]`}>
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input
              ref={passwordRef}
              type={showPw ? 'text' : 'password'}
              placeholder="Password"
              autoComplete="current-password"
              className={`${AUTH_INPUT} pr-12`}
              required
            />
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

        <motion.button
          type="submit"
          disabled={loading}
          whileTap={{ scale: loading ? 1 : 0.98 }}
          className={AUTH_PRIMARY_BUTTON}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {loading ? 'Signing in...' : 'Sign in'}
        </motion.button>
      </form>

      <div className="mt-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-white/[0.12]" />
        <span className="text-xs font-semibold text-white/48">or continue with</span>
        <div className="h-px flex-1 bg-white/[0.12]" />
      </div>

      <button
        type="button"
        onClick={() => {
          window.location.href = getGithubOAuthUrl();
        }}
        className={`mt-4 ${AUTH_SECONDARY_BUTTON}`}
      >
        <GithubIcon />
        Continue with GitHub
      </button>

      <p className="mt-6 text-center text-xs font-semibold text-white/58">
        No account?{' '}
        <Link to="/auth/register" className={AUTH_LINK}>
          Create one free
        </Link>
      </p>
    </AuthLayout>
  );
}

function GithubIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}
