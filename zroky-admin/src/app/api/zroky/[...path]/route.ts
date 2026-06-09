import { NextRequest } from "next/server";

const devDefaultBaseUrl = "http://127.0.0.1:8000";
const defaultTimeoutMs = 10_000;
const OWNER_TOKEN_COOKIE = "zroky_owner_token";

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

function getBaseUrl(): string {
  const raw = process.env.ZROKY_API_BASE_URL;
  const isProduction = process.env.NODE_ENV === "production";
  const allowLocalProductionBaseUrl = process.env.ZROKY_ALLOW_LOCAL_API_BASE_URL === "1";

  if (!raw && isProduction) {
    throw new Error("ZROKY_API_BASE_URL is required in production.");
  }

  const value = raw ?? devDefaultBaseUrl;
  const parsed = new URL(value);
  if (
    isProduction
    && !allowLocalProductionBaseUrl
    && ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname)
  ) {
    throw new Error("ZROKY_API_BASE_URL must point to a real backend in production.");
  }

  const normalized = parsed.toString();
  return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
}

async function forwardRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const params = await context.params;
  const path = params.path.join("/");
  let baseUrl: string;
  try {
    baseUrl = getBaseUrl();
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Backend API is not configured." },
      { status: 500 },
    );
  }
  const target = new URL(`${baseUrl}/${path}`);

  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value);
  });

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }

  const ownerToken = request.cookies.get(OWNER_TOKEN_COOKIE)?.value;
  if (ownerToken) {
    headers.set("x-zroky-admin-token", ownerToken);
  }

  const timeoutMsRaw = Number(process.env.ZROKY_API_PROXY_TIMEOUT_MS ?? defaultTimeoutMs);
  const timeoutMs = Number.isFinite(timeoutMsRaw) && timeoutMsRaw > 0 ? timeoutMsRaw : defaultTimeoutMs;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
    signal: controller.signal,
  };

  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    const bodyText = await request.text();
    if (bodyText.length > 0) {
      init.body = bodyText;
    }
  }

  let response: Response;
  try {
    response = await fetch(target, init);
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return Response.json(
      {
        detail: timedOut
          ? `Backend API timed out after ${timeoutMs}ms.`
          : "Backend API is unavailable. Start the Zroky backend and retry.",
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }

  const location = response.headers.get("location");
  if (location && response.status >= 300 && response.status < 400) {
    return new Response(null, {
      status: response.status,
      headers: {
        location,
      },
    });
  }

  const responseContentType = response.headers.get("content-type") ?? "application/json";

  if ([204, 205, 304].includes(response.status)) {
    return new Response(null, {
      status: response.status,
    });
  }

  if (responseContentType.includes("text/event-stream") && response.body) {
    const streamHeaders = new Headers();
    streamHeaders.set("content-type", responseContentType);
    streamHeaders.set("cache-control", "no-cache, no-transform");
    streamHeaders.set("connection", "keep-alive");

    return new Response(response.body, {
      status: response.status,
      headers: streamHeaders,
    });
  }

  const responseText = await response.text();

  const outboundHeaders = new Headers();
  outboundHeaders.set("content-type", responseContentType);

  return new Response(responseText, {
    status: response.status,
    headers: outboundHeaders,
  });
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}
