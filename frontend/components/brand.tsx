import Link from "next/link";

import { cn } from "@/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "group inline-flex items-baseline gap-2 rounded-sm outline-none",
        "focus-visible:ring-2 focus-visible:ring-sodium focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        className,
      )}
    >
      <span className="font-display text-lg font-semibold tracking-tight text-foreground">
        Voyanta
      </span>
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full bg-sodium transition-colors group-hover:bg-foreground"
      />
    </Link>
  );
}

/** A monospace eyebrow, set like a row label on a timetable. */
export function RuleLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={cn("rule-label", className)}>{children}</span>;
}
