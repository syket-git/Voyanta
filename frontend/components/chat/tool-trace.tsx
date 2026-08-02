"use client";

import { ChevronRight, Globe, Plane } from "lucide-react";
import { useState } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { TraceEntry } from "@/hooks/use-chat";
import { cn } from "@/lib/utils";

const TOOL_LABELS: Record<string, { label: string; icon: typeof Plane }> = {
  search_flights: { label: "Live flight board", icon: Plane },
  web_search: { label: "Web search", icon: Globe },
};

function formatArgs(args?: Record<string, unknown>) {
  if (!args) return "";

  return Object.entries(args)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}=${String(value)}`)
    .join("  ");
}

function TraceRow({ entry }: { entry: TraceEntry }) {
  const [open, setOpen] = useState(false);
  const meta = TOOL_LABELS[entry.name] ?? { label: entry.name, icon: Globe };
  const Icon = meta.icon;
  const args = formatArgs(entry.args);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        disabled={!entry.preview}
        className={cn(
          "flex w-full items-center gap-3 px-3 py-2 text-left transition-colors",
          entry.preview ? "hover:bg-secondary/60" : "cursor-default",
        )}
      >
        <Icon
          aria-hidden
          className={cn(
            "size-3.5 shrink-0",
            entry.settled ? "text-muted-foreground" : "text-sodium",
          )}
        />
        <span className="shrink-0 whitespace-nowrap font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-foreground/80">
          {meta.label}
        </span>
        {args ? (
          <span className="hidden min-w-0 truncate font-mono text-[0.6875rem] text-muted-foreground sm:inline">
            {args}
          </span>
        ) : null}

        <span className="ml-auto flex shrink-0 items-center gap-2">
          {entry.settled ? (
            <span className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
              done
            </span>
          ) : (
            <span className="animate-sodium-pulse font-mono text-[0.625rem] uppercase tracking-[0.14em] text-sodium">
              checking
            </span>
          )}
          {entry.preview ? (
            <ChevronRight
              aria-hidden
              className={cn(
                "size-3.5 text-muted-foreground transition-transform",
                open && "rotate-90",
              )}
            />
          ) : null}
        </span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <pre className="overflow-x-auto border-t border-border/60 bg-background/60 px-3 py-2.5 font-mono text-[0.6875rem] leading-relaxed text-muted-foreground whitespace-pre-wrap">
          {entry.preview}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ToolTrace({ trace }: { trace: TraceEntry[] }) {
  if (!trace.length) return null;

  return (
    <div className="mb-3 divide-y divide-border/60 overflow-hidden rounded-md border border-border bg-card">
      {trace.map((entry, index) => (
        <TraceRow key={`${entry.name}-${index}`} entry={entry} />
      ))}
    </div>
  );
}
