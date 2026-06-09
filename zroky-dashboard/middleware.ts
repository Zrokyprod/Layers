import type { NextRequest } from "next/server";

import { guardDashboardRoute } from "./src/lib/route-auth-guard";

export function middleware(request: NextRequest) {
  return guardDashboardRoute(request);
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
