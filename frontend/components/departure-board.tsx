import { cn } from "@/lib/utils";

interface Row {
  day: string;
  slot: string;
  place: string;
  detail: string;
}

const ROWS: Row[] = [
  { day: "01", slot: "Morning", place: "Canggu", detail: "Batu Bolong beach, coffee at Crate" },
  { day: "01", slot: "Evening", place: "Seminyak", detail: "Sunset at La Plancha" },
  { day: "02", slot: "Morning", place: "Ubud", detail: "Tegallalang rice terraces" },
  { day: "02", slot: "Evening", place: "Ubud", detail: "Campuhan ridge walk" },
  { day: "03", slot: "Morning", place: "Uluwatu", detail: "" },
];

/**
 * The signature element: an itinerary set as an airport departure board, with the last
 * row still resolving. Rows flap in on load; the stagger is CSS-only.
 */
export function DepartureBoard() {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-[0.6875rem] font-medium tracking-[0.18em] text-sodium">
            DAC → DPS
          </span>
          <span className="rule-label">3 nights · 2 travellers</span>
        </div>
        <span className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
          Sample
        </span>
      </div>

      <div className="hidden grid-cols-[3rem_6rem_9rem_1fr] gap-4 border-b border-border/60 px-4 py-2 sm:grid sm:px-5">
        {["Day", "When", "Where", "What"].map((heading) => (
          <span key={heading} className="rule-label">
            {heading}
          </span>
        ))}
      </div>

      <div className="divide-y divide-border/60">
        {ROWS.map((row, index) => {
          const resolving = !row.detail;

          return (
            <div
              key={`${row.day}-${row.slot}`}
              style={{ animationDelay: `${140 + index * 90}ms` }}
              className={cn(
                "animate-flap-in grid grid-cols-[3rem_1fr] gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[3rem_6rem_9rem_1fr] sm:gap-y-0 sm:px-5",
                resolving && "bg-sodium/[0.04]",
              )}
            >
              <span className="font-mono text-sm font-medium tabular-nums text-sodium">
                {row.day}
              </span>
              <span className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted-foreground sm:self-center">
                {row.slot}
              </span>
              <span className="col-start-2 font-medium text-foreground sm:col-start-auto">
                {row.place}
              </span>
              <span className="col-start-2 text-sm text-muted-foreground sm:col-start-auto sm:self-center">
                {resolving ? (
                  <span className="animate-sodium-pulse font-mono text-[0.6875rem] uppercase tracking-[0.16em] text-sodium">
                    checking the board…
                  </span>
                ) : (
                  row.detail
                )}
              </span>
            </div>
          );
        })}
      </div>

      <div className="border-t border-border px-4 py-3 sm:px-5">
        <p className="font-mono text-[0.6875rem] leading-relaxed tracking-[0.04em] text-muted-foreground">
          Fares shown anywhere in a plan are{" "}
          <span className="text-sodium">estimates with a source</span>, never numbers the
          model made up.
        </p>
      </div>
    </div>
  );
}
