"use client";

import { Check, Loader2 } from "lucide-react";

import { useBilling } from "@/components/billing/billing-provider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const BENEFITS = [
  "Enough trips to plan every journey you take",
  "Live flight lookups and web search on every turn",
  "Your whole thread history, kept and searchable",
];

export function UpgradeDialog({
  open,
  onOpenChange,
  reason,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  reason: string | null;
}) {
  const { status, goToCheckout, redirecting } = useBilling();

  // The backend's refusal message names the actual number and plan, so it is better
  // copy than anything written here in advance.
  const description =
    reason ??
    (status
      ? `You've used ${status.turns_used} of your ${status.turns_limit} free trips this month.`
      : "Your free trips for this month are spent.");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-xl tracking-tight">
            Keep planning
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="rounded-md border border-border bg-card p-4">
          <div className="flex items-baseline justify-between">
            <span className="rule-label">Voyanta Pro</span>
            <span className="font-display text-lg font-semibold tracking-tight">
              {status?.price_label ?? "—"}
            </span>
          </div>

          <ul className="mt-3 space-y-2">
            {BENEFITS.map((benefit) => (
              <li key={benefit} className="flex gap-2.5 text-sm leading-6 text-foreground/85">
                <Check aria-hidden className="mt-1 size-3.5 shrink-0 text-sodium" />
                {benefit}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs leading-5 text-muted-foreground">
          Payment is handled by Stripe — card details never reach Voyanta. Cancel any time
          from the sidebar.
        </p>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Not now
          </Button>
          <Button onClick={goToCheckout} disabled={redirecting || !status?.billing_enabled}>
            {redirecting ? (
              <>
                <Loader2 aria-hidden className="size-3.5 animate-spin" />
                Opening Stripe
              </>
            ) : (
              `Upgrade — ${status?.price_label ?? ""}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
