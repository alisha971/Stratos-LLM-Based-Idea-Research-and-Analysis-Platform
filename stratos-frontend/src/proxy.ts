import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE_NAME = "stratos_token";

// Next.js 16 renamed the `middleware` convention to `proxy`. This is only an
// optimistic cookie-existence gate for /app routes — real auth is enforced by
// the backend JWT check on every API call.
export function proxy(request: NextRequest) {
  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*"],
};
