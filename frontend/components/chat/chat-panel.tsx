"use client";

import { Plus } from "lucide-react";
import { useEffect, useRef } from "react";

import { Wordmark } from "@/components/brand";
import { Composer } from "@/components/chat/composer";
import { MessageRow } from "@/components/chat/message-row";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";

const OPENERS = [
  "Five days in Bali from Dhaka, mid-March, around $1,200 for two",
  "A week in Japan in cherry blossom season, first time, mid budget",
  "Long weekend in Kathmandu — what can I actually see in three days?",
];

export function ChatPanel() {
  const { messages, threadId, isStreaming, isRestoring, send, stop, reset } = useChat();
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
    if (pinnedRef.current) {
      bottomRef.current?.scrollIntoView({ block: "end" });
    }
  }, [messages]);

  const empty = !messages.length && !isRestoring;

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border px-4 py-3">
        <Wordmark />

        <div className="flex items-center gap-3">
          {threadId ? (
            <span
              title={threadId}
              className="hidden font-mono text-[0.6875rem] tracking-[0.08em] text-muted-foreground sm:inline"
            >
              thread {threadId.slice(0, 8)}
            </span>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={reset}
            disabled={isStreaming || !messages.length}
            className="gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
          >
            <Plus aria-hidden className="size-3.5" />
            New trip
          </Button>
        </div>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8">
          {empty ? (
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
