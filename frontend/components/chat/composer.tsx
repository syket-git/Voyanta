"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MAX_MESSAGE_LENGTH } from "@/lib/voyanta";
import { cn } from "@/lib/utils";

export function Composer({
  onSend,
  onStop,
  isStreaming,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [value]);

  const tooLong = value.length > MAX_MESSAGE_LENGTH;
  const canSend = value.trim().length > 0 && !tooLong && !isStreaming;

  function submit() {
    if (!canSend) return;
    onSend(value);
    setValue("");
  }

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur">
      <div className="mx-auto w-full max-w-3xl px-4 py-4">
        <div
          className={cn(
            "rounded-lg border bg-card transition-colors",
            tooLong ? "border-destructive" : "border-border focus-within:border-sodium/60",
          )}
        >
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="Where to, from where, and roughly when?"
            aria-label="Describe your trip"
            className={cn(
              // The auto-resize effect measures the value, not the placeholder, so an
              // empty field needs a floor tall enough for the placeholder to wrap into.
              "min-h-[3.25rem] resize-none border-0 bg-transparent px-4 py-3.5 text-[0.9375rem] shadow-none",
              "focus-visible:ring-0 dark:bg-transparent",
            )}
          />

          <div className="flex items-center justify-between gap-3 px-3 pb-3">
            <span
              className={cn(
                "min-w-0 truncate font-mono text-[0.6875rem] tracking-[0.08em]",
                tooLong ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {tooLong ? (
                `${value.length} / ${MAX_MESSAGE_LENGTH} — too long to send`
              ) : (
                <>
                  Enter to send
                  <span className="hidden sm:inline"> · Shift+Enter for a new line</span>
                </>
              )}
            </span>

            {isStreaming ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onStop}
                className="gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
              >
                <Square aria-hidden className="size-3 fill-current" />
                Stop
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={submit}
                disabled={!canSend}
                aria-label="Send message"
                className="gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
              >
                Plan
                <ArrowUp aria-hidden className="size-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
