const rawDashboardUrl = import.meta.env.VITE_DASHBOARD_URL ?? 'https://app.zroky.com';

export const DASHBOARD_URL = rawDashboardUrl.replace(/\/$/, '');
export const SIGN_IN_URL = `${DASHBOARD_URL}/login`;
export const FORGOT_PASSWORD_URL = `${DASHBOARD_URL}/forgot-password`;
export const RESET_PASSWORD_URL = `${DASHBOARD_URL}/reset-password`;
export const VERIFY_EMAIL_URL = `${DASHBOARD_URL}/verify-email`;

export function buildSignUpUrl(params: Record<string, string | undefined> = {}) {
  const url = new URL(`${DASHBOARD_URL}/signup`);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
  }
  return url.toString();
}

export const SIGN_UP_URL = buildSignUpUrl();

const AUTH_ALIASES: Record<string, string> = {
  '/auth': '/login',
  '/auth/login': '/login',
  '/auth/register': '/signup',
  '/auth/forgot-password': '/forgot-password',
  '/auth/check-email': '/verify-email',
  '/auth/reset-password': '/reset-password',
  '/auth/verify-email': '/verify-email',
  '/login': '/login',
  '/signup': '/signup',
  '/forgot-password': '/forgot-password',
  '/reset-password': '/reset-password',
  '/verify-email': '/verify-email',
};

export function isDashboardAuthAlias(pathname: string) {
  return pathname === '/auth' || pathname.startsWith('/auth/') || pathname in AUTH_ALIASES;
}

export function buildDashboardAuthUrl(pathname: string, search = '') {
  const canonicalPath = AUTH_ALIASES[pathname] ?? '/login';
  return `${DASHBOARD_URL}${canonicalPath}${search}`;
}
