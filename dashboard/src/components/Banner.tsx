import type { Polled } from "../hooks/usePolling";
import type { Status } from "../api/types.gen";

/** What the banner slot should say, or null when everything is fine. */
export function bannerMessage(polled: Polled<Status>): string | null {
  if (polled.data === null) {
    return polled.error ? "Cannot reach the monitor. Retrying." : "Waiting for the monitor.";
  }
  if (polled.stale) {
    const seconds = Math.round((Date.now() - (polled.lastSuccessAt ?? Date.now())) / 1000);
    return `Showing the last data, ${seconds} s old. The monitor has not answered.`;
  }
  const offline = polled.data.nodes.filter((n) => n.state === "offline").map((n) => n.id);
  if (offline.length > 0) return `Offline: ${offline.join(", ")}. Data may have gaps.`;
  return null;
}

export const BANNER_HEIGHT = "3rem";

/**
 * The reserved banner slot. It has the same height with or without a message, so a stale or
 * offline state never shifts the page (the layout never jumps).
 */
export function Banner({ polled }: { polled: Polled<Status> }) {
  const message = bannerMessage(polled);
  return (
    <div
      data-testid="banner-slot"
      style={{ height: BANNER_HEIGHT }}
      className="flex items-center overflow-hidden"
    >
      {message ? (
        <p
          role="status"
          className="w-full rounded-md border border-line bg-level-yellow-bg px-4 py-2 text-sm font-medium text-level-yellow"
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
