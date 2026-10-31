import { useState } from "react";
import { api } from "../api/client";
import type { Events as EventsData } from "../api/types.gen";
import { usePolling } from "../hooks/usePolling";
import { clockTimeSeconds } from "../lib/format";
import { DOMAIN_NAME } from "../lib/levels";

type Event = EventsData["events"][number];
type Kind = Event["kind"];

const KIND_LABEL: Record<Kind, string> = {
  spike: "Spike",
  drift: "Drift",
  correlation: "Link",
  sim_event: "Simulated event",
  checkin: "Check-in",
  node: "Node",
};

const FILTERS: { key: "all" | Kind; label: string }[] = [
  { key: "all", label: "All" },
  { key: "spike", label: "Spikes" },
  { key: "drift", label: "Drifts" },
  { key: "correlation", label: "Links" },
  { key: "sim_event", label: "Simulated events" },
  { key: "checkin", label: "Check-ins" },
  { key: "node", label: "Nodes" },
];

/** The event log, newest first. Check-ins are context: they never change a level. */
export default function Events() {
  const { data, error } = usePolling((s) => api.events({ limit: 500 }, s), 10_000);
  const [filter, setFilter] = useState<"all" | Kind>("all");

  const events = [...(data?.events ?? [])]
    .filter((e) => filter === "all" || e.kind === filter)
    .sort((a, b) => b.t - a.t);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold tracking-tight">Events</h1>
      <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
              filter === f.key
                ? "border-accent bg-panel text-ink ring-2 ring-accent"
                : "border-line text-muted"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <section
        aria-label="Event log"
        className="rounded-xl border border-line bg-panel p-2 shadow-sm"
      >
        {!data ? (
          <p className="p-3 text-muted">
            {error ? "Could not load the events." : "Loading the events."}
          </p>
        ) : events.length === 0 ? (
          <p className="p-3 text-muted">No events to show.</p>
        ) : (
          <ol className="divide-y divide-line">
            {events.map((e) => (
              <li
                key={e.id}
                data-testid={`event-${e.id}`}
                data-kind={e.kind}
                className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 ${
                  e.kind === "checkin" ? "text-muted" : ""
                }`}
              >
                <time
                  className="w-20 shrink-0 font-mono text-sm"
                  dateTime={new Date(e.t * 1000).toISOString()}
                >
                  {clockTimeSeconds(e.t)}
                </time>
                <span className="w-36 shrink-0 text-sm font-semibold">
                  {KIND_LABEL[e.kind]}
                  {e.kind === "checkin" ? <span className="font-normal"> (context)</span> : null}
                </span>
                <span className="min-w-0 flex-1 text-base">{e.sentence}</span>
                <span className="flex gap-2 text-xs text-muted">
                  {e.crew ? <span>{e.crew}</span> : null}
                  {e.domain ? <span>{DOMAIN_NAME[e.domain]}</span> : null}
                  {e.simulated ? (
                    <span
                      data-testid={`simulated-${e.id}`}
                      className="rounded-full border border-accent px-2 py-0.5 font-semibold text-accent"
                    >
                      Simulated
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
