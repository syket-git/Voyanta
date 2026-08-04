/**
 * Client for the Voyanta backend.
 *
 * Every call goes through the Next.js proxy at /api/voyanta, never straight to FastAPI,
 * so the backend origin stays server-side and requests are same-origin.
 */

export type Role = "user" | "assistant" | "tool" | "system";

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
}

export interface MessageOut {
  id: string;
  role: Role;
  content: string;
  tool_calls: ToolCallInfo[];
}

export interface ThreadHistory {
  thread_id: string;
  messages: MessageOut[];
}

export interface User {
  id: string;
  email: string;
}

export interface ThreadSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface BillingStatus {
  plan: "free" | "pro";
  plan_label: string;
  turns_used: number;
  turns_limit: number;
  turns_remaining: number;
  /** Renewal date on Pro, the first of next month on Free. */
  period_end: string;
  price_label: string;
  subscription_status: string | null;
  billing_enabled: boolean;
  manageable: boolean;
}

export type StreamEvent =
  | { type: "metadata"; thread_id: string; run_id: string }
  | { type: "token"; content: string }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "tool_end"; name: string; preview: string }
  // `upgrade` marks the one failure the reader can do something about: the monthly
  // allowance is spent, so the UI offers a plan rather than a retry.
  | { type: "error"; message: string; run_id?: string; upgrade?: boolean }
  | { type: "done"; thread_id: string; run_id: string };

const API = "/api/voyanta";

/** The backend caps `message` at 4000 characters; mirror it so the UI can warn first. */
export const MAX_MESSAGE_LENGTH = 4000;

async function failure(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.error ?? body?.detail;

    // FastAPI validation errors arrive as a list of per-field objects.
    if (Array.isArray(detail)) {
      return detail[0]?.msg ?? `Request failed (${response.status})`;
    }

    return typeof detail === "string" ? detail : `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });

  if (!response.ok) throw new Error(await failure(response));

  return response.status === 204 ? (undefined as T) : response.json();
}

/**
 * Stream one turn.
 *
 * `EventSource` cannot be used here — it only issues GET requests, and the turn is a
 * POST. So the body is read frame by frame instead.
 */
export async function* streamChat(
  input: { message: string; threadId?: string },
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: input.message, thread_id: input.threadId }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    // 402 is the backend saying the allowance is spent. It arrives as a normal JSON
    // response rather than an SSE frame, because the refusal happens before the stream.
    yield {
      type: "error",
      message: await failure(response),
      upgrade: response.status === 402,
    };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // A frame is only complete once its blank-line terminator has arrived; anything
      // after the last one is a partial frame and has to wait for the next read.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) yield event;
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let name = "";
  const data: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }

  if (!name) return null;

  try {
    return { type: name, ...JSON.parse(data.join("\n") || "{}") } as StreamEvent;
  } catch {
    return null;
  }
}

export function signup(email: string, password: string): Promise<User> {
  return request("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<User> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}

export function listThreads(): Promise<ThreadSummary[]> {
  return request("/threads");
}

export function renameThread(threadId: string, title: string): Promise<ThreadSummary> {
  return request(`/threads/${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function fetchThread(threadId: string): Promise<ThreadHistory | null> {
  const response = await fetch(`${API}/threads/${encodeURIComponent(threadId)}`);

  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await failure(response));

  return response.json();
}

export async function deleteThread(threadId: string): Promise<void> {
  const response = await fetch(`${API}/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });

  if (!response.ok && response.status !== 404) throw new Error(await failure(response));
}

export function fetchBillingStatus(): Promise<BillingStatus> {
  return request("/billing/status");
}

/** Both of these return a Stripe-hosted URL; the caller navigates the browser to it. */
export function startCheckout(): Promise<{ url: string }> {
  return request("/billing/checkout", { method: "POST" });
}

export function openBillingPortal(): Promise<{ url: string }> {
  return request("/billing/portal", { method: "POST" });
}

export function sendFeedback(
  runId: string,
  score: 0 | 1,
  comment?: string,
): Promise<void> {
  return request("/feedback", {
    method: "POST",
    body: JSON.stringify({ run_id: runId, score, comment }),
  });
}
