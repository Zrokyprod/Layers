# Zroky Dashboard

Next.js dashboard for Home, Calls, Cost, Alerts, Settings, plus onboarding/auth support flows.

## Run Local

```bash
npm install
npm run dev
```

Dashboard default URL: http://localhost:3000

## Environment Variables

Create `.env.local` with:

```bash
# Backend base URL used by the /api/zroky proxy
ZROKY_API_BASE_URL=http://127.0.0.1:8000

# Optional server-side fallback for single-project local smoke/testing only.
# Do not use these for normal authenticated customer dashboard traffic.
ZROKY_PROJECT_ID=
ZROKY_API_KEY=

# UI labels
NEXT_PUBLIC_DASHBOARD_ENV=staging
NEXT_PUBLIC_DASHBOARD_PROJECT_LABEL=project
```

For production, set `ZROKY_API_BASE_URL` on the dashboard server/runtime to
the deployed backend origin, for example `https://api.zroky.com`. Do not rely on
`NEXT_PUBLIC_*` API URL variables for dashboard proxy traffic; `/api/zroky/*`
and auth refresh routes are server-side proxies and read `ZROKY_API_BASE_URL`
only.

## GitHub OAuth Redirect (Required)

Set backend env `GITHUB_OAUTH_REDIRECT_URL` to:

```bash
http://localhost:3000/auth/github/callback
```

If backend and dashboard run on different domains, use the exact deployed dashboard callback URL.

## Auth Guard

- Protected routes: `/`, `/home`, `/calls`, `/cost`, `/alerts`, `/settings`
- Public routes: `/auth/*`, `/onboarding`
- Session token is stored in cookie `zroky_access_token`

Unauthenticated access to protected routes redirects to `/auth/login?next=<path>`.
