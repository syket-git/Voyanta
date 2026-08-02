import { ArrowRight, Globe, Plane } from "lucide-react";
import Link from "next/link";

import { RuleLabel, Wordmark } from "@/components/brand";
import { DepartureBoard } from "@/components/departure-board";
import { Button } from "@/components/ui/button";

const RULES = [
  {
    heading: "It will not invent a price",
    body: "No made-up fares, flight numbers, departure times or opening hours. If a tool did not return it, the plan says so and offers to look it up.",
  },
  {
    heading: "Every figure carries its source",
    body: "Costs come from a live web search and are labelled as estimates, with the link they came from. You can check the number before you budget around it.",
  },
  {
    heading: "It admits when a lookup fails",
    body: "When the flight board is empty or a search returns nothing, you get told plainly — not a confident paragraph quietly filling the gap.",
  },
];

const TOOLS = [
  {
    icon: Plane,
    name: "search_flights",
    heading: "The live flight board",
    body: "Reads real departures between two airports: airline, flight number, status, terminal, gate and delay. It resolves “Bali” or “Japan” to the right airport, and returns an error rather than guessing when it can’t.",
    note: "Status only — this board carries no fares.",
  },
  {
    icon: Globe,
    name: "web_search",
    heading: "Everything else",
    body: "Attractions, sample routes, visa rules, seasonal weather, local transport, food and safety. Fare and hotel estimates come from here too, which is why they arrive with a citation attached.",
    note: "Returns five sources per lookup.",
  },
];

export default function Home() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-3.5">
          <Wordmark />
          <Button
            render={<Link href="/chat" />}
            size="sm"
            className="gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
          >
            Plan a trip
            <ArrowRight aria-hidden className="size-3.5" />
          </Button>
        </div>
      </header>

      <main>
        <section className="border-b border-border">
          <div className="mx-auto w-full max-w-5xl px-6 pt-16 pb-14 sm:pt-24 sm:pb-20">
            <RuleLabel>A tour planner that shows its working</RuleLabel>

            <h1 className="mt-6 max-w-3xl font-display text-[clamp(2.5rem,7vw,4.5rem)] leading-[0.98] font-semibold tracking-[-0.03em] text-balance">
              Itineraries you can
              <br className="hidden sm:block" />{" "}
              <span className="text-sodium">check.</span>
            </h1>

            <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground text-pretty">
              Most travel assistants will happily quote you a fare that does not exist.
              Voyanta reads the live flight board, cites what it finds, and tells you when
              it doesn&apos;t know.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Button
                render={<Link href="/chat" />}
                size="lg"
                className="h-11 gap-2 px-5 font-mono text-xs uppercase tracking-[0.12em]"
              >
                Plan a trip
                <ArrowRight aria-hidden className="size-4" />
              </Button>
              <Button
                render={<a href="#rules" />}
                size="lg"
                variant="outline"
                className="h-11 px-5 font-mono text-xs uppercase tracking-[0.12em]"
              >
                What it refuses to do
              </Button>
            </div>
          </div>
        </section>

        <section className="border-b border-border bg-background">
          <div className="mx-auto w-full max-w-5xl px-6 py-14 sm:py-20">
            <div className="mb-6 flex items-baseline justify-between gap-4">
              <RuleLabel>A reply, mid-flight</RuleLabel>
              <span className="rule-label hidden sm:inline">Bali · March</span>
            </div>
            <DepartureBoard />
          </div>
        </section>

        <section id="rules" className="border-b border-border scroll-mt-16">
          <div className="mx-auto w-full max-w-5xl px-6 py-14 sm:py-20">
            <RuleLabel>Rules it cannot break</RuleLabel>
            <h2 className="mt-5 max-w-2xl font-display text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
              The useful part is what it leaves out.
            </h2>

            <div className="mt-12 grid gap-px overflow-hidden rounded-lg border border-border sm:grid-cols-3">
              {RULES.map((rule, index) => (
                <div key={rule.heading} className="bg-card p-6">
                  <span className="font-mono text-sm font-medium tabular-nums text-sodium">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-4 font-display text-lg font-semibold tracking-tight text-foreground text-balance">
                    {rule.heading}
                  </h3>
                  <p className="mt-2.5 text-sm leading-7 text-muted-foreground">
                    {rule.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-border">
          <div className="mx-auto w-full max-w-5xl px-6 py-14 sm:py-20">
            <RuleLabel>Two instruments</RuleLabel>
            <h2 className="mt-5 max-w-2xl font-display text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
              One reads the board. One reads the web.
            </h2>

            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {TOOLS.map((tool) => {
                const Icon = tool.icon;

                return (
                  <div
                    key={tool.name}
                    className="rounded-lg border border-border bg-card p-6"
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon aria-hidden className="size-4 text-sodium" />
                      <span className="font-mono text-[0.6875rem] tracking-[0.14em] text-muted-foreground">
                        {tool.name}
                      </span>
                    </div>

                    <h3 className="mt-5 font-display text-xl font-semibold tracking-tight text-foreground">
                      {tool.heading}
                    </h3>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">
                      {tool.body}
                    </p>

                    <p className="mt-5 border-t border-border pt-4 font-mono text-[0.6875rem] tracking-[0.06em] text-sodium">
                      {tool.note}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section>
          <div className="mx-auto w-full max-w-5xl px-6 py-20 sm:py-28">
            <div className="max-w-xl">
              <h2 className="font-display text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
                Tell it where you&apos;re starting from.
              </h2>
              <p className="mt-4 leading-8 text-muted-foreground text-pretty">
                Origin, rough dates, and what you have to spend is enough to begin. It
                will ask for the rest as it goes.
              </p>
              <Button
                render={<Link href="/chat" />}
                size="lg"
                className="mt-8 h-11 gap-2 px-5 font-mono text-xs uppercase tracking-[0.12em]"
              >
                Plan a trip
                <ArrowRight aria-hidden className="size-4" />
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-6">
          <span className="rule-label">Voyanta · LangGraph + FastAPI</span>
          <span className="rule-label">Flight status via AviationStack · Search via Tavily</span>
        </div>
      </footer>
    </div>
  );
}
