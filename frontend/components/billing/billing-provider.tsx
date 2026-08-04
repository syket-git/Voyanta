"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { UpgradeDialog } from "@/components/billing/upgrade-dialog";
import {
  fetchBillingStatus,
  openBillingPortal,
  startCheckout,
  type BillingStatus,
} from "@/lib/voyanta";

interface BillingContextValue {
  status: BillingStatus | null;
  refresh: () => Promise<void>;
  /** Raise the upgrade dialog. `reason` is the backend's own wording when it refused. */
  promptUpgrade: (reason?: string) => void;
  goToCheckout: () => Promise<void>;
  goToPortal: () => Promise<void>;
  redirecting: boolean;
}

const BillingContext = createContext<BillingContextValue | null>(null);

/**
 * Stripe's webhook and the browser's redirect race each other, and the redirect usually
 * wins. Without a short poll the user lands back on a page that still says "Free"
 * moments after paying, which reads as a failed payment.
 */
const CONFIRM_ATTEMPTS = 6;
const CONFIRM_INTERVAL_MS = 1500;

export function useBilling() {
  const context = useContext(BillingContext);

  if (!context) {
    throw new Error("useBilling must be used inside BillingProvider.");
  }

  return context;
}

export function BillingProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [redirecting, setRedirecting] = useState(false);

  const router = useRouter();
  const searchParams = useSearchParams();
  const checkout = searchParams.get("checkout");
  const confirmedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await fetchBillingStatus());
    } catch {
      // The meter is not worth interrupting the conversation over; the backend refuses
      // on its own if the allowance really is spent.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchBillingStatus()
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!checkout || confirmedRef.current) return;

    confirmedRef.current = true;
    router.replace("/chat");

    if (checkout !== "success") {
      toast("Checkout cancelled. Nothing was charged.");
      return;
    }

    let cancelled = false;

    (async () => {
      for (let attempt = 0; attempt < CONFIRM_ATTEMPTS; attempt++) {
        if (cancelled) return;

        try {
          const next = await fetchBillingStatus();
          setStatus(next);

          if (next.plan === "pro") {
            toast.success("You're on Pro. Plan away.");
            return;
          }
        } catch {
          // Keep polling — a single failed read says nothing about the subscription.
        }

        await new Promise((resolve) => setTimeout(resolve, CONFIRM_INTERVAL_MS));
      }

      if (!cancelled) {
        toast("Payment received. Your plan will update in a moment.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [checkout, router]);

  const promptUpgrade = useCallback((message?: string) => {
    setReason(message ?? null);
    setOpen(true);
  }, []);

  // Both of these hand the browser to Stripe. `redirecting` stays true on the way out:
  // the page is being replaced, so re-enabling the button would only invite a second tab.
  const goToCheckout = useCallback(async () => {
    setRedirecting(true);

    try {
      const { url } = await startCheckout();
      window.location.href = url;
    } catch (error) {
      setRedirecting(false);
      toast.error((error as Error).message || "Could not reach Stripe. Try again.");
    }
  }, []);

  const goToPortal = useCallback(async () => {
    setRedirecting(true);

    try {
      const { url } = await openBillingPortal();
      window.location.href = url;
    } catch (error) {
      setRedirecting(false);
      toast.error((error as Error).message || "Could not open billing. Try again.");
    }
  }, []);

  return (
    <BillingContext.Provider
      value={{ status, refresh, promptUpgrade, goToCheckout, goToPortal, redirecting }}
    >
      {children}
      <UpgradeDialog open={open} onOpenChange={setOpen} reason={reason} />
    </BillingContext.Provider>
  );
}
