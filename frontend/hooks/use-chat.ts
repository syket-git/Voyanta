"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchThread,
  streamChat,
  type MessageOut,
  type ToolCallInfo,
} from "@/lib/voyanta";

export interface TraceEntry {
  name: string;
  args?: Record<string, unknown>;
  preview?: string;
  settled: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  runId?: string;
  trace: TraceEntry[];
  failed?: boolean;
}

/**
 * Re-parsing markdown on every token is wasted work — tokens arrive far faster than a
 * reader can follow. Text accumulates in a ref and flushes to state on this interval.
 */
const FLUSH_INTERVAL_MS = 60;

function makeId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function fromHistory(messages: MessageOut[]): ChatMessage[] {
  const restored: ChatMessage[] = [];

  for (const message of messages) {
    if (message.role === "user") {
      restored.push({
        id: message.id || makeId(),
        role: "user",
        content: message.content,
        trace: [],
      });
      continue;
    }

    if (message.role !== "assistant") continue;

    // An assistant turn that only carries tool calls has no prose to show; fold its
    // calls into the reply that follows so the trace still appears.
    const trace: TraceEntry[] = message.tool_calls.map((call: ToolCallInfo) => ({
      name: call.name,
      args: call.args,
      settled: true,
    }));

    const pending = restored.at(-1);

    if (!message.content.trim()) {
      restored.push({ id: message.id || makeId(), role: "assistant", content: "", trace });
    } else if (pending?.role === "assistant" && !pending.content) {
      pending.content = message.content;
      pending.trace.push(...trace);
    } else {
      restored.push({
        id: message.id || makeId(),
        role: "assistant",
        content: message.content,
        trace,
      });
    }
  }

  return restored.filter((m) => m.role === "user" || m.content || m.trace.length);
}

export function useChat({
  threadId: routeThreadId,
  onThreadCreated,
  onTurnComplete,
}: {
  threadId: string | null;
  onThreadCreated?: (threadId: string) => void;
  onTurnComplete?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(Boolean(routeThreadId));

  // The live thread id. It diverges from the route on the very first message, when the
  // backend mints a thread and the URL is corrected without a navigation.
  const threadRef = useRef<string | null>(routeThreadId);
  const abortRef = useRef<AbortController | null>(null);
  const bufferRef = useRef("");
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Loads once per thread. Switching threads remounts this hook via a `key` on the
  // workspace, which is React's own answer to "reset state when a prop changes" and
  // avoids resetting through an effect.
  useEffect(() => {
    if (!routeThreadId) return;

    let cancelled = false;

    fetchThread(routeThreadId)
      .then((history) => {
        if (!cancelled && history) setMessages(fromHistory(history.messages));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [routeThreadId]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (flushTimerRef.current) clearInterval(flushTimerRef.current);
    };
  }, []);

  const updateLast = useCallback(
    (mutate: (message: ChatMessage) => ChatMessage) =>
      setMessages((current) => {
        if (!current.length) return current;
        const next = [...current];
        next[next.length - 1] = mutate(next[next.length - 1]);
        return next;
      }),
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      bufferRef.current = "";
      setIsStreaming(true);
      setMessages((current) => [
        ...current,
        { id: makeId(), role: "user", content: trimmed, trace: [] },
        { id: makeId(), role: "assistant", content: "", trace: [] },
      ]);

      const flush = () => {
        if (!bufferRef.current) return;
        const pending = bufferRef.current;
        bufferRef.current = "";
        updateLast((message) => ({ ...message, content: message.content + pending }));
      };

      flushTimerRef.current = setInterval(flush, FLUSH_INTERVAL_MS);

      let created = false;

      try {
        for await (const event of streamChat(
          { message: trimmed, threadId: threadRef.current ?? undefined },
          { signal: controller.signal },
        )) {
          switch (event.type) {
            case "metadata":
              if (!threadRef.current) {
                threadRef.current = event.thread_id;
                created = true;
                onThreadCreated?.(event.thread_id);
              }
              updateLast((message) => ({ ...message, runId: event.run_id }));
              break;

            case "token":
              bufferRef.current += event.content;
              break;

            case "tool_start":
              flush();
              updateLast((message) => ({
                ...message,
                trace: [
                  ...message.trace,
                  { name: event.name, args: event.args, settled: false },
                ],
              }));
              break;

            case "tool_end":
              updateLast((message) => {
                const trace = [...message.trace];
                const open = trace.findLastIndex(
                  (entry) => entry.name === event.name && !entry.settled,
                );
                if (open >= 0) {
                  trace[open] = { ...trace[open], preview: event.preview, settled: true };
                }
                return { ...message, trace };
              });
              break;

            case "error":
              flush();
              updateLast((message) => ({
                ...message,
                failed: true,
                content:
                  message.content ||
                  "The planner hit an error partway through. Try sending that again.",
              }));
              break;

            case "done":
              flush();
              break;
          }
        }
      } catch (error) {
        if ((error as Error)?.name !== "AbortError") {
          updateLast((message) => ({
            ...message,
            failed: true,
            content: message.content || "Could not reach the planner. Check the backend.",
          }));
        }
      } finally {
        if (flushTimerRef.current) clearInterval(flushTimerRef.current);
        flushTimerRef.current = null;
        flush();
        setIsStreaming(false);
        abortRef.current = null;
        // A new thread needs a title in the sidebar; an existing one needs reordering.
        if (created || threadRef.current) onTurnComplete?.();
      }
    },
    [isStreaming, onThreadCreated, onTurnComplete, updateLast],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, isStreaming, isLoading, send, stop };
}
