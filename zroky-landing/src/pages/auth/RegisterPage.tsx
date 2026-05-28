import { useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { RegisterScene } from '../../components/auth/AuthScenes';
import { registerUser, getGithubOAuthUrl } from '../../lib/auth-api';

const INPUT = 'block w-full rounded-xl border border-panel-border bg-white px-4 py-3 text-sm font-bold text-primary placeholder:font-normal placeholder:text-tertiary transition duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';
const LABEL = 'mb-1.5 block text-xs font-extrabold uppercase tracking-[0.12em] text-tertiary';

export default function RegisterPage() {
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const firstNameRef = useRef<HTMLInputElement>(null);
  const lastNameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const companyRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await registerUser({
        email: emailRef.current?.value?.trim() ?? '',
        password: passwordRef.current?.value ?? '',
        first_name: firstNameRef.current?.value?.trim(),
        last_name: lastNameRef.current?.value?.trim(),
        company: companyRef.current?.value?.trim(),
      });
      navigate('/auth/check-email');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please try again.');
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      scene={<RegisterScene />}
      tagline="Your agents are shipping. Start capturing failures before they become incidents."
      caption="Connect in under 5 minutes — one decorator, zero infrastructure changes."
    >
      <div>
        <h1 className="text-2xl font-black text-primary">Create your workspace</h1>
        <p className="mt-1.5 text-sm font-bold text-secondary">
          Free forever. No credit card needed.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-600">
          {error}
        </div>
      )}

      <form className="mt-4 space-y-5" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL}>First name</label>
            <input ref={firstNameRef} type="text" placeholder="Aryan" autoComplete="given-name" className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Last name</label>
            <input ref={lastNameRef} type="text" placeholder="Shah" autoComplete="family-name" className={INPUT} />
          </div>
        </div>

        <div>
          <label className={LABEL}>Work email</label>
          <input ref={emailRef} type="email" placeholder="you@company.com" autoComplete="email" className={INPUT} required />
        </div>

        <div>
          <label className={LABEL}>Company name <span className="text-tertiary normal-case font-bold">(optional)</span></label>
          <input ref={companyRef} type="text" placeholder="Acme AI" autoComplete="organization" className={INPUT} />
        </div>

        <div>
          <label className={LABEL}>Password</label>
          <div className="relative">
            <input
              ref={passwordRef}
              type={showPw ? 'text' : 'password'}
              placeholder="Min. 12 characters"
              autoComplete="new-password"
              className={`${INPUT} pr-12`}
              required
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-tertiary transition hover:text-primary"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <PasswordStrength />
        </div>

        <div className="flex items-start gap-2.5">
          <input id="terms" type="checkbox" required className="mt-0.5 h-4 w-4 rounded border-panel-border accent-accent" />
          <label htmlFor="terms" className="text-xs font-bold text-secondary leading-5">
            I agree to the{' '}
            <a href="#" className="font-extrabold text-accent hover:underline">Terms of Service</a>
            {' '}and{' '}
            <a href="#" className="font-extrabold text-accent hover:underline">Privacy Policy</a>
          </label>
        </div>

        <motion.button
          type="submit"
          disabled={loading}
          whileTap={{ scale: loading ? 1 : 0.98 }}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-primary py-3 text-sm font-extrabold text-white shadow-sm transition duration-200 hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {loading ? 'Creating account…' : 'Create account'}
        </motion.button>
      </form>

      <div className="mt-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-panel-border" />
        <span className="text-xs font-bold text-tertiary">or</span>
        <div className="h-px flex-1 bg-panel-border" />
      </div>

      <button
        type="button"
        onClick={() => { window.location.href = getGithubOAuthUrl(); }}
        className="mt-4 flex w-full items-center justify-center gap-3 rounded-full border border-panel-border bg-white py-3 text-sm font-extrabold text-primary transition duration-200 hover:bg-canvas hover:border-accent/30"
      >
        <GithubIcon />
        Continue with GitHub
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

function PasswordStrength() {
  return (
    <div className="mt-2 flex gap-1">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className={`h-1 flex-1 rounded-full transition-all duration-300 ${
            i === 0 ? 'bg-danger' : 'bg-panel-border'
          }`}
        />
      ))}
    </div>
  );
}

function GithubIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}
