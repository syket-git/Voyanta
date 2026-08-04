"use client";

import { useCallback, useEffect, useRef } from "react";

import { useBilling } from "@/components/billing/billing-provider";
import { Composer } from "@/components/chat/composer";
import { MessageRow } from "@/components/chat/message-row";
import { useThreads } from "@/components/chat/threads-provider";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useChat } from "@/hooks/use-chat";

const OPENERS = [
  "Five days in Bali from Dhaka, mid-March, around $1,200 for two",
  "A week in Japan in cherry blossom season, first time, mid budget",
  "Long weekend in Kathmandu — what can I actually see in three days?",
];

export function ChatWorkspace({ threadId }: { threadId: string | null }) {
  const { refresh } = useThreads();
  const { refresh: refreshBilling, promptUpgrade } = useBilling();

  // The backend mints the thread on the first message. Correcting the URL with
  // replaceState rather than a router navigation is deliberate: navigating here would
  // unmount this component and kill the in-flight stream.
  const onThreadCreated = useCallback((id: string) => {
    window.history.replaceState(null, "", `/chat/${id}`);
  }, []);

  // The turn was counted server-side before the reply started, so the meter is stale the
  // moment a turn ends.
  const onTurnComplete = useCallback(() => {
    refresh();
    refreshBilling();
  }, [refresh, refreshBilling]);

  const { messages, isStreaming, isLoading, send, stop } = useChat({
    threadId,
    onThreadCreated,
    onTurnComplete,
    onQuotaExceeded: promptUpgrade,
  });

  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Follow the stream, but stop following the moment the reader scrolls up to re-read.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;

    function onScroll() {
      const distance = node!.scrollHeight - node!.scrollTop - node!.clientHeight;
      pinnedRef.current = distance < 120;
    }

    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (pinnedRef.current) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const empty = !messages.length && !isLoading;

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-3">
        <SidebarTrigger />
        <span className="rule-label">Voyanta</span>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8">
          {isLoading ? (
            <div className="space-y-4 pt-6">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : empty ? (
            <div className="pt-10 pb-4">
              <p className="rule-label">Departures</p>
              <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-balance">
                Where are you going?
              </h1>
              <p className="mt-3 max-w-lg leading-7 text-muted-foreground">
                Tell me where you&apos;re starting from, roughly when, and what you have to
                spend. I&apos;ll check the live flight board, look up what&apos;s worth
                your time, and show you where each figure came from.
              </p>

              <div className="mt-8 space-y-px overflow-hidden rounded-md border border-border">
                {OPENERS.map((opener) => (
                  <button
                    key={opener}
                    type="button"
                    onClick={() => send(opener)}
                    className="flex w-full items-center gap-3 bg-card px-4 py-3.5 text-left text-sm text-foreground/85 transition-colors hover:bg-secondary hover:text-foreground focus-visible:bg-secondary focus-visible:outline-none"
                  >
                    <span aria-hidden className="h-1 w-1 shrink-0 rounded-full bg-sodium" />
                    {opener}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-8">
              {messages.map((message, index) => (
                <MessageRow
                  key={message.id}
                  message={message}
                  isStreaming={isStreaming && index === messages.length - 1}
                />
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <Composer onSend={send} onStop={stop} isStreaming={isStreaming} />
    </div>
  );
}
