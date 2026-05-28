const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL ?? 'http://localhost:3000';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
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

export function redirectToDashboard(tokens: AuthTokens): void {
  const params = new URLSearchParams({
    at: tokens.access_token,
    rt: tokens.refresh_token,
    at_exp: String(tokens.access_expires_in_seconds ?? 259200),
    rt_exp: String(tokens.refresh_expires_in_seconds ?? 2592000),
    ev: String(tokens.email_verified ?? true),
  });
  window.location.href = `${DASHBOARD_URL}/auth/handoff?${params.toString()}`;
}

export function getGithubOAuthUrl(): string {
  return `${DASHBOARD_URL}/api/zroky/v1/auth/github/start`;
}
