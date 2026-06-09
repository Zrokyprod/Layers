const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL ?? 'http://localhost:3000';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
  token_type?: string;
  user_id?: string;
  email?: string | null;
  email_verified?: boolean;
}

export async function loginWithPassword(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? 'Invalid email or password');
  }
  return res.json() as Promise<AuthTokens>;
}

export async function registerUser(data: {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  company?: string;
}): Promise<void> {
  const res = await fetch(`${API_URL}/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? 'Registration failed. Please try again.');
  }
}

export async function redirectToDashboard(tokens: AuthTokens): Promise<void> {
  const res = await fetch(`${API_URL}/v1/auth/session/handoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tokens),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? 'Could not create dashboard session');
  }

  const body = await res.json() as { handoff_id?: string };
  if (!body.handoff_id) {
    throw new Error('Could not create dashboard session');
  }

  const params = new URLSearchParams({ handoff_id: body.handoff_id });
  window.location.href = `${DASHBOARD_URL}/auth/oauth/callback?${params.toString()}`;
}

export function getGithubOAuthUrl(): string {
  return `${DASHBOARD_URL}/api/zroky/v1/auth/github/start`;
}
