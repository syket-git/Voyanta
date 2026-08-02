import { cookies } from "next/headers";

import type { User } from "@/lib/voyanta";

/**
 * Server-side session read.
 *
 * Talks to the backend directly rather than through the proxy route, because a server
 * component has no origin to make a relative request against. `proxy.ts` only checks
 * that a cookie exists; this asks the backend whether it is actually valid.
 */
const BACKEND_URL = process.env.VOYANTA_API_URL ?? "http://127.0.0.1:8000";
const SESSION_COOKIE = "voyanta_session";

export async function getUser(): Promise<User | null> {
  const token = (await cookies()).get(SESSION_COOKIE);

  if (!token) return null;

  try {
    const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
      headers: { cookie: `${SESSION_COOKIE}=${token.value}` },
      cache: "no-store",
    });

    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}
