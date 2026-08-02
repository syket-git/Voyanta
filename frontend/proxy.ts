import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Optimistic route protection only.
 *
 * This checks that a session cookie exists, not that it is valid — it exists to avoid
 * flashing the app at a signed-out visitor. The backend authorises every request against
 * the session table, and that is what actually protects the data.
 */
const SESSION_COOKIE = "voyanta_session";

export function proxy(request: NextRequest) {
  const signedIn = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  if (!signedIn && pathname.startsWith("/chat")) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  if (signedIn && (pathname === "/login" || pathname === "/signup")) {
    return NextResponse.redirect(new URL("/chat", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/chat/:path*", "/login", "/signup"],
};
