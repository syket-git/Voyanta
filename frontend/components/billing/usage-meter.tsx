"use client";

import { useBilling } from "@/components/billing/billing-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function UsageMeter() {
  const { status, promptUpgrade, goToPortal, redirecting } = useBilling();

  if (!status) {
    return <Skeleton className="h-11 w-full" />;
  }

  if (status.plan === "pro") {
    return (
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="rule-label">Pro</p>
          <p className="truncate text-[0.6875rem] text-muted-foreground">
            Renews {formatDate(status.period_end)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={goToPortal}
          disabled={redirecting}
          className="font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
        >
          Manage
        </Button>
      </div>
    );
  }

  const used = Math.min(status.turns_used, status.turns_limit);
  const fraction = status.turns_limit > 0 ? used / status.turns_limit : 1;
  const low = status.turns_remaining <= 3;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="rule-label">Free plan</span>
        <span
          className={cn(
            "font-mono text-[0.6875rem] tabular-nums",
            low ? "text-sodium" : "text-muted-foreground",
          )}
        >
          {used}/{status.turns_limit}
        </span>
      </div>

      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={status.turns_limit}
        aria-valuenow={used}
        aria-label="Trips used this month"
        className="h-1 w-full overflow-hidden rounded-full bg-secondary"
      >
        <div
          className={cn("h-full transition-[width]", low ? "bg-sodium" : "bg-foreground/40")}
          style={{ width: `${Math.round(fraction * 100)}%` }}
        />
      </div>

      {status.billing_enabled ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => promptUpgrade()}
          className="h-7 w-full justify-start px-1 font-mono text-[0.6875rem] uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground"
        >
          {status.turns_remaining > 0
            ? `${status.turns_remaining} left · Upgrade`
            : `Resets ${formatDate(status.period_end)} · Upgrade`}
        </Button>
      ) : (
        <p className="px-1 text-[0.6875rem] text-muted-foreground">
          Resets {formatDate(status.period_end)}
        </p>
      )}
    </div>
  );
}
