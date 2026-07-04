const DEFAULT_POST_AUTH_PATH = "/home";
const PROTECTED_AGENT_SETUP_PATH = "/agents/setup";
const PROTECTED_AGENT_INTENT = "protect-agent";
const SAFE_TOKEN_PATTERN = /^[a-z0-9_-]{1,48}$/i;
const PLAN_CODES = new Set(["free", "starter", "pro", "enterprise"]);

type SearchParamsReader = Pick<URLSearchParams, "get">;

export const POST_AUTH_REDIRECT_COOKIE = "zroky_post_auth_redirect";

export function isSafeAppPath(value: string | null | undefined): value is string {
  if (!value) return false;
  const path = value.trim();
  if (!path.startsWith("/") || path.startsWith("//")) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return false;
  return true;
}

export function safeAppPath(value: string | null | undefined, fallback = DEFAULT_POST_AUTH_PATH): string {
  return isSafeAppPath(value) ? value.trim() : fallback;
}

function cleanToken(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return SAFE_TOKEN_PATTERN.test(trimmed) ? trimmed : null;
}

function cleanPlan(value: string | null | undefined): string | null {
  const token = cleanToken(value)?.toLowerCase() ?? null;
  return token && PLAN_CODES.has(token) ? token : null;
}

export function buildProtectedAgentSetupPath(params?: SearchParamsReader): string {
  const query = new URLSearchParams({ intent: PROTECTED_AGENT_INTENT });
  const plan = cleanPlan(params?.get("plan"));
  const source = cleanToken(params?.get("source"));

  if (plan) query.set("plan", plan);
  if (source) query.set("source", source);

  return `${PROTECTED_AGENT_SETUP_PATH}?${query.toString()}`;
}

export function resolveSignupRedirectPath(params: SearchParamsReader, fallback = DEFAULT_POST_AUTH_PATH): string {
  const explicitNext = safeAppPath(params.get("next"), "");
  if (explicitNext) return explicitNext;

  const intent = cleanToken(params.get("intent"));
  const source = cleanToken(params.get("source"));
  if (intent === PROTECTED_AGENT_INTENT || source?.startsWith("pricing")) {
    return buildProtectedAgentSetupPath(params);
  }

  return fallback;
}

export function isProtectedAgentSignupIntent(params: SearchParamsReader): boolean {
  return resolveSignupRedirectPath(params, "").startsWith(`${PROTECTED_AGENT_SETUP_PATH}?`);
}

export function buildLoginHref(nextPath: string): string {
  const safeNext = safeAppPath(nextPath, "");
  if (!safeNext || safeNext === DEFAULT_POST_AUTH_PATH) return "/login";
  return `/login?next=${encodeURIComponent(safeNext)}`;
}

export function buildSignupHref(nextPath: string): string {
  const safeNext = safeAppPath(nextPath, "");
  if (!safeNext || safeNext === DEFAULT_POST_AUTH_PATH) return "/signup";
  return `/signup?next=${encodeURIComponent(safeNext)}`;
}

export function buildVerifyEmailHref(email: string, nextPath: string): string {
  const query = new URLSearchParams();
  if (email) query.set("email", email);

  const safeNext = safeAppPath(nextPath, "");
  if (safeNext && safeNext !== DEFAULT_POST_AUTH_PATH) {
    query.set("next", safeNext);
  }

  const serialized = query.toString();
  return serialized ? `/verify-email?${serialized}` : "/verify-email";
}
