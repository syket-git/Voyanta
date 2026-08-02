import type { NextRequest } from "next/server";

/**
 * Proxies every /api/voyanta/* call to the FastAPI backend.
 *
 * Routing through the server keeps the backend origin out of the browser and makes the
 * requests same-origin, so CORS never applies. It is also the seam to attach a session
 * to — the backend trusts `user_id` from the request body, so it must be set here rather
 * than by the client, once there is auth to derive it from.
 */

const BACKEND_URL = process.env.VOYANTA_API_URL ?? "http://127.0.0.1:8000";

// Streaming replies must not be buffered or cached anywhere in between.
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: RouteContext<"/api/voyanta/[...path]">,
) {
  const { path } = await context.params;
  const target = new URL(`/api/${path.join("/")}`, BACKEND_URL);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("x-request-id", requestId);

  // The session lives in this cookie. Without forwarding it the backend sees every
  // request as anonymous.
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  let upstream: Response;

  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      // Buffered rather than streamed: request bodies here are small JSON payloads, and
      // forwarding a stream would require half-duplex support from the runtime.
      body: request.method === "GET" || request.method === "DELETE"
        ? undefined
        : await request.text(),
      signal: request.signal,
      cache: "no-store",
    });
  } catch (error) {
    console.error(`voyanta proxy: ${request.method} ${target.pathname} failed`, error);
    return Response.json(
      { error: "Cannot reach the Voyanta API. Is the backend running?" },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const header of ["content-type", "cache-control", "x-request-id"]) {
    const value = upstream.headers.get(header);
    if (value) responseHeaders.set(header, value);
  }

  // getSetCookie() keeps multiple Set-Cookie headers separate; reading them as one
  // joined string would corrupt any cookie whose value contains a comma.
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }

  responseHeaders.set("x-accel-buffering", "no");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

// Every verb the client uses must be exported by name — Next answers 405 for any that
// is not, and the request never reaches the backend.
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
