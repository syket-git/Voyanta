"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { RuleLabel, Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login, signup } from "@/lib/voyanta";

const COPY = {
  login: {
    eyebrow: "Welcome back",
    heading: "Pick up where you left off.",
    action: "Sign in",
    switchPrompt: "No account yet?",
    switchLabel: "Create one",
    switchHref: "/signup",
  },
  signup: {
    eyebrow: "Create an account",
    heading: "Start planning.",
    action: "Create account",
    switchPrompt: "Already have an account?",
    switchLabel: "Sign in",
    switchHref: "/login",
  },
} as const;

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const copy = COPY[mode];
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;

    setPending(true);
    setError(null);

    try {
      await (mode === "login" ? login : signup)(email, password);
      // refresh() so the server re-reads the new session cookie before navigating.
      router.replace(searchParams.get("next") || "/chat");
      router.refresh();
    } catch (caught) {
      setError((caught as Error).message);
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col bg-background">
      <header className="border-b border-border px-6 py-3.5">
        <Wordmark />
      </header>

      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <RuleLabel>{copy.eyebrow}</RuleLabel>
          <h1 className="mt-4 font-display text-3xl font-semibold tracking-tight text-balance">
            {copy.heading}
          </h1>

          <form onSubmit={onSubmit} className="mt-9 space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="rule-label">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="rule-label">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={mode === "signup" ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={mode === "signup" ? "At least 8 characters" : "••••••••"}
              />
            </div>

            {error ? (
              <p
                role="alert"
                className="border-l-2 border-destructive pl-3 text-sm leading-6 text-destructive"
              >
                {error}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={pending}
              className="h-10 w-full gap-2 font-mono text-xs uppercase tracking-[0.12em]"
            >
              {pending ? "Working…" : copy.action}
              {pending ? null : <ArrowRight aria-hidden className="size-3.5" />}
            </Button>
          </form>

          <p className="mt-7 text-sm text-muted-foreground">
            {copy.switchPrompt}{" "}
            <Link
              href={copy.switchHref}
              className="font-medium text-sodium underline decoration-sodium/40 underline-offset-4 hover:decoration-sodium"
            >
              {copy.switchLabel}
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
