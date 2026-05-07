import { NextRequest } from "next/server";

const defaultBaseUrl = "http://127.0.0.1:8000";

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

function getBaseUrl(): string {
  const raw = process.env.ZROKY_API_BASE_URL ?? defaultBaseUrl;
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

async function forwardRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const params = await context.params;
  const path = params.path.join("/");
  const baseUrl = getBaseUrl();
  const target = new URL(`${baseUrl}/${path}`);

  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value);
  });

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }

  const incomingAuth = request.headers.get("authorization");
  const cookieToken = request.cookies.get("zroky_access_token")?.value;
  if (incomingAuth) {
    headers.set("authorization", incomingAuth);
  } else if (cookieToken) {
    const bearer = cookieToken.toLowerCase().startsWith("bearer ") ? cookieToken : `Bearer ${cookieToken}`;
    headers.set("authorization", bearer);
  }

  // Forward owner/admin token when present (used by the Owner Dashboard)
  const adminToken = request.headers.get("x-zroky-admin-token");
  if (adminToken) {
    headers.set("x-zroky-admin-token", adminToken);
  }

  const projectId = process.env.ZROKY_PROJECT_ID;
  const apiKey = process.env.ZROKY_API_KEY;
  const provisioningToken = process.env.ZROKY_PROVISIONING_TOKEN;
  const provisioningHeader = process.env.ZROKY_PROVISIONING_TOKEN_HEADER ?? "x-provisioning-token";

  if (projectId) {
    headers.set("x-project-id", projectId);
  }

  if (apiKey) {
    headers.set("x-api-key", apiKey);
  }

  if (provisioningToken) {
    headers.set(provisioningHeader, provisioningToken);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    const bodyText = await request.text();
    if (bodyText.length > 0) {
      init.body = bodyText;
    }
  }

  const response = await fetch(target, init);
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

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  return forwardRequest(request, context);
}
