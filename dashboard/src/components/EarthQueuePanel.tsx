import { useState } from "react";
import { api } from "../api/client";
import type { EarthQueue, EarthQueueItem } from "../api/types.gen";
import { useStatusContext } from "../hooks/StatusContext";
import { usePolling } from "../hooks/usePolling";
import { formatDuration } from "../lib/format";

const TIER_WORD: Record<EarthQueueItem["tier"], string> = {
  crew_only: "Crew only",
  flight_surgeon: "Flight surgeon",
  urgent: "Urgent",
};

function stateWord(item: EarthQueueItem): string {
  if (item.sent) return "Sent";
  return item.approved ? "Approved, waiting for the next window" : "Waiting for approval";
}

/** Summaries queued for Earth. Nothing leaves the vehicle until a crew member approves it. */
export function EarthQueuePanel() {
  const { data: status } = useStatusContext();
  const { data: queue, error, refresh } = usePolling<EarthQueue>((s) => api.earthQueue(s), 10_000);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [confirmed, setConfirmed] = useState<Record<string, EarthQueueItem>>({});
  const [failed, setFailed] = useState<string | null>(null);

  async function approve(item: EarthQueueItem) {
    setFailed(null);
    setPending((p) => new Set(p).add(item.id)); // optimistic: show it approved at once
    try {
      const approved = await api.approve(item.id);
      setConfirmed((c) => ({ ...c, [item.id]: approved })); // keep it approved until the poll agrees
      refresh();
    } catch {
      setFailed(item.id); // roll back: the item is shown as it really is
    } finally {
      setPending((p) => {
        const next = new Set(p);
        next.delete(item.id);
        return next;
      });
    }
  }

  const items = [...(queue?.items ?? [])].sort(
    (a, b) => Number(a.approved) - Number(b.approved) || b.t - a.t,
  );
  const untilWindow =
    queue && status ? formatDuration(Math.max(queue.next_window_t - status.t, 0)) : null;

  return (
    <section
      aria-label="Earth queue"
      className="rounded-xl border border-line bg-panel p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold">Earth queue</h2>
        <p data-testid="window-countdown" className="text-sm text-muted">
          {untilWindow ? `Next comms window in ${untilWindow}` : "Next comms window unknown"}
        </p>
      </div>
      {failed ? (
        <p
          role="alert"
          className="mt-2 rounded-md bg-level-red-bg px-3 py-2 text-sm text-level-red"
        >
          Could not approve {failed}. It is still waiting for approval. Try again.
        </p>
      ) : null}
      {!queue ? (
        <p className="mt-3 text-muted">
          {error ? "Could not load the queue." : "Loading the queue."}
        </p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-muted">Nothing is waiting for Earth.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-line">
          {items.map((item) => {
            const known = item.approved ? item : (confirmed[item.id] ?? item);
            const optimistic = pending.has(item.id);
            const shown: EarthQueueItem = optimistic ? { ...known, approved: true } : known;
            return (
              <li
                key={item.id}
                data-testid={`queue-${item.id}`}
                className="flex flex-col gap-2 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm">
                    <span className="font-semibold">{TIER_WORD[item.tier]}</span>
                    <span className="text-muted"> · {item.bytes} bytes · </span>
                    <span data-testid={`queue-state-${item.id}`}>{stateWord(shown)}</span>
                  </p>
                  <button
                    type="button"
                    disabled={shown.approved}
                    onClick={() => void approve(item)}
                    className="rounded-md border border-line bg-panel px-3 py-1.5 text-sm font-medium enabled:hover:border-accent disabled:text-muted"
                  >
                    {shown.approved ? "Approved" : "Approve"}
                  </button>
                </div>
                <p className="text-sm">{item.summary}</p>
                <details className="text-sm">
                  <summary className="cursor-pointer text-muted">What would be sent</summary>
                  <pre className="mt-1 overflow-x-auto rounded-md bg-surface p-2 text-xs">
                    {JSON.stringify(item.payload, null, 2)}
                  </pre>
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
