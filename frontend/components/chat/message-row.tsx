"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { ToolTrace } from "@/components/chat/tool-trace";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/hooks/use-chat";
import { sendFeedback } from "@/lib/voyanta";
import { cn } from "@/lib/utils";

function Feedback({ runId }: { runId: string }) {
  const [score, setScore] = useState<0 | 1 | null>(null);
  const [pending, setPending] = useState(false);

  async function rate(next: 0 | 1) {
    if (pending || score !== null) return;
    setPending(true);

    try {
      await sendFeedback(runId, next);
      setScore(next);
      toast.success(next === 1 ? "Marked as helpful" : "Marked as unhelpful");
    } catch {
      toast.error("Could not record that. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-4 flex items-center gap-1">
      <span className="rule-label mr-1">
        {score === null ? "Was this useful" : "Thanks"}
      </span>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Helpful"
        disabled={pending || score !== null}
        onClick={() => rate(1)}
        className={cn("size-7", score === 1 && "text-sodium")}
      >
        <ThumbsUp aria-hidden className="size-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Not helpful"
        disabled={pending || score !== null}
        onClick={() => rate(0)}
        className={cn("size-7", score === 0 && "text-sodium")}
      >
        <ThumbsDown aria-hidden className="size-3.5" />
      </Button>
    </div>
  );
}

export function MessageRow({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg rounded-br-sm border border-border bg-secondary px-4 py-2.5 text-[0.9375rem] leading-7 text-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  const waiting = isStreaming && !message.content;

  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2">
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 rounded-full bg-sodium",
            isStreaming && "animate-sodium-pulse",
          )}
        />
        <span className="rule-label">Voyanta</span>
      </div>

      <ToolTrace trace={message.trace} />

      {waiting ? (
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.16em] text-muted-foreground">
          <span className="animate-sodium-pulse">Reading the board…</span>
        </p>
      ) : (
        <div className={cn(message.failed && "text-destructive")}>
          <Markdown>{message.content}</Markdown>
        </div>
      )}

      {message.runId && !isStreaming && message.content && !message.failed ? (
        <Feedback runId={message.runId} />
      ) : null}
    </div>
  );
}
