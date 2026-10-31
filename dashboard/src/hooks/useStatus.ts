import { api } from "../api/client";
import type { Status } from "../api/types.gen";
import { usePolling, type Polled } from "./usePolling";

/** `/api/status`, polled every 5 s; stale after 15 s without a success. */
export function useStatus(): Polled<Status> {
  return usePolling((signal) => api.status(signal));
}
