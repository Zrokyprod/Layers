import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, Github, Loader2 } from 'lucide-react';
import AuthLayout from '../../components/auth/AuthLayout';
import { RegisterScene } from '../../components/auth/AuthScenes';
import { getGithubOAuthUrl, registerUser } from '../../lib/auth-api';
import { AUTH_INPUT, AUTH_LABEL, AUTH_LINK, AUTH_PRIMARY_BUTTON, AUTH_SECONDARY_BUTTON } from './authStyles';

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
      tagline="Your agents are shipping. Start capturing failures before they become repeated incidents."
      caption="Create a workspace, capture first, and connect provider keys only when verified replay needs them."
    >
      <div>
        <h1 className="text-2xl font-semibold text-white">Create your workspace</h1>
        <p className="mt-1.5 text-sm font-semibold leading-6 text-white/62">Start with capture. No credit card required.</p>
      </div>

      {error ? (
        <div className="mt-5 rounded-lg border border-blocked/35 bg-blocked/10 px-4 py-3 text-sm font-semibold text-blocked">
          {error}
        </div>
      ) : null}

      <form className="mt-5 space-y-5" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={AUTH_LABEL}>First name</label>
            <input ref={firstNameRef} type="text" placeholder="Aryan" autoComplete="given-name" className={AUTH_INPUT} />
          </div>
          <div>
            <label className={AUTH_LABEL}>Last name</label>
            <input ref={lastNameRef} type="text" placeholder="Shah" autoComplete="family-name" className={AUTH_INPUT} />
          </div>
        </div>

        <div>
          <label className={AUTH_LABEL}>Work email</label>
          <input ref={emailRef} type="email" placeholder="you@company.com" autoComplete="email" className={AUTH_INPUT} required />
        </div>

        <div>
          <label className={AUTH_LABEL}>
            Company name <span className="normal-case text-white/42">(optional)</span>
          </label>
          <input ref={companyRef} type="text" placeholder="Acme AI" autoComplete="organization" className={AUTH_INPUT} />
        </div>

        <div>
          <label className={AUTH_LABEL}>Password</label>
          <div className="relative">
            <input
              ref={passwordRef}
              type={showPw ? 'text' : 'password'}
              placeholder="Min. 12 characters"
              autoComplete="new-password"
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
          <PasswordStrength />
        </div>

        <div className="flex items-start gap-2.5">
          <input id="terms" type="checkbox" required className="mt-0.5 h-4 w-4 rounded border-white/[0.2] bg-black accent-white" />
          <label htmlFor="terms" className="text-xs font-semibold leading-5 text-white/62">
            I agree to the{' '}
            <a href="#" className={AUTH_LINK}>
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="#" className={AUTH_LINK}>
              Privacy Policy
            </a>
          </label>
        </div>

        <motion.button type="submit" disabled={loading} whileTap={{ scale: loading ? 1 : 0.98 }} className={AUTH_PRIMARY_BUTTON}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          {loading ? 'Creating account...' : 'Create account'}
        </motion.button>
      </form>

      <div className="mt-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-white/[0.12]" />
        <span className="text-xs font-semibold text-white/48">or</span>
        <div className="h-px flex-1 bg-white/[0.12]" />
      </div>

      <button
        type="button"
        onClick={() => {
          window.location.href = getGithubOAuthUrl();
        }}
        className={`mt-4 ${AUTH_SECONDARY_BUTTON}`}
      >
        <Github className="h-4 w-4" />
        Continue with GitHub
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

function PasswordStrength() {
  return (
    <div className="mt-2 flex gap-1">
      {[...Array(4)].map((_, index) => (
        <div key={index} className={`h-1 flex-1 rounded-full transition-all duration-300 ${index === 0 ? 'bg-white' : 'bg-white/[0.14]'}`} />
      ))}
    </div>
  );
}
