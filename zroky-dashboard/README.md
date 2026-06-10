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

# Optional server-side fallback project context for proxy calls
ZROKY_PROJECT_ID=
ZROKY_API_KEY=

# Optional project provisioning token pass-through
ZROKY_PROVISIONING_TOKEN=
ZROKY_PROVISIONING_TOKEN_HEADER=x-provisioning-token

# UI labels
NEXT_PUBLIC_DASHBOARD_ENV=staging
NEXT_PUBLIC_DASHBOARD_PROJECT_LABEL=project

# Browser-safe Razorpay Standard Checkout key id only.
# Do not put RAZORPAY_KEY_SECRET in the dashboard environment.
NEXT_PUBLIC_RAZORPAY_KEY_ID=
```

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
