import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * The agent replies in markdown: `### Day 1 — title` headings, a budget table, and
 * cited links. Each of those gets the timetable treatment rather than browser defaults.
 */
const components: Components = {
  h1: ({ className, ...props }) => (
    <h1
      className={cn("font-display text-2xl font-semibold text-foreground", className)}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn(
        "mt-8 font-display text-xl font-semibold tracking-tight text-foreground",
        className,
      )}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={cn(
        "mt-7 border-l-2 border-sodium pl-3 font-display text-lg font-semibold tracking-tight text-foreground",
        className,
      )}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p className={cn("leading-7 text-foreground/85", className)} {...props} />
  ),
  // The dash marker is scoped to `ul` here rather than set on `li`, so ordered items
  // keep their numbers instead of getting a number and a dash.
  ul: ({ className, ...props }) => (
    <ul
      className={cn(
        "space-y-1.5 pl-0",
        "[&>li]:relative [&>li]:pl-4",
        "[&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[0.85em]",
        "[&>li]:before:h-px [&>li]:before:w-2 [&>li]:before:bg-border",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn(
        "list-decimal space-y-1.5 pl-5 marker:font-mono marker:text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  li: ({ className, ...props }) => (
    <li className={cn("leading-7 text-foreground/85", className)} {...props} />
  ),
  strong: ({ className, ...props }) => (
    <strong className={cn("font-semibold text-foreground", className)} {...props} />
  ),
  a: ({ className, ...props }) => (
    <a
      target="_blank"
      rel="noreferrer noopener"
      className={cn(
        "font-medium text-sodium underline decoration-sodium/40 underline-offset-4",
        "transition-colors hover:decoration-sodium",
        className,
      )}
      {...props}
    />
  ),
  code: ({ className, ...props }) => (
    <code
      className={cn(
        "rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-[0.85em] text-foreground",
        className,
      )}
      {...props}
    />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "overflow-x-auto rounded-md border border-border bg-secondary p-4 font-mono text-sm",
        className,
      )}
      {...props}
    />
  ),
  table: ({ className, ...props }) => (
    <div className="my-5 overflow-x-auto rounded-md border border-border">
      <table className={cn("w-full border-collapse text-sm", className)} {...props} />
    </div>
  ),
  thead: ({ className, ...props }) => (
    <thead className={cn("bg-secondary/60", className)} {...props} />
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        "border-b border-border px-4 py-2.5 text-left font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td
      className={cn(
        "border-b border-border/60 px-4 py-2.5 align-top text-foreground/85",
        className,
      )}
      {...props}
    />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "border-l-2 border-border pl-4 text-muted-foreground italic",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("my-7 border-border", className)} {...props} />
  ),
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-3.5 text-[0.9375rem]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
