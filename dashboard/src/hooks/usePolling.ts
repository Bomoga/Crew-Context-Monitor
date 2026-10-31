import { useCallback, useEffect, useRef, useState } from "react";

export const POLL_MS = 5_000;
export const STALE_MS = 15_000;

export interface Polled<T> {
  /** The last successful response; kept while later requests fail. */
  data: T | null;
  /** The most recent failure, cleared by the next success. */
  error: Error | null;
  /** True when the last success is older than `staleMs` (or there has been none for that long). */
  stale: boolean;
  /** Epoch milliseconds of the last success, or null. */
  lastSuccessAt: number | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Calls `fetcher` now and then every `intervalMs`, aborting a request that is still in flight
 * when the next one starts and everything on unmount.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs = POLL_MS,
  staleMs = STALE_MS,
): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [startedAt] = useState(() => Date.now());
  const fetcherRef = useRef(fetcher);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const poll = useCallback(() => {
    controller.current?.abort();
    const mine = new AbortController();
    controller.current = mine;
    fetcherRef
      .current(mine.signal)
      .then((value) => {
        if (mine.signal.aborted) return;
        setData(value);
        setError(null);
        setLastSuccessAt(Date.now());
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (mine.signal.aborted) return;
        setError(e instanceof Error ? e : new Error(String(e)));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    poll();
    const pollTimer = setInterval(poll, intervalMs);
    const clockTimer = setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      clearInterval(pollTimer);
      clearInterval(clockTimer);
      controller.current?.abort();
    };
  }, [poll, intervalMs]);

  const reference = lastSuccessAt ?? startedAt;
  return {
    data,
    error,
    stale: now - reference > staleMs,
    lastSuccessAt,
    loading,
    refresh: poll,
  };
}
