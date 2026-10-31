import { createContext, useContext, type ReactNode } from "react";
import type { Status } from "../api/types.gen";
import type { Polled } from "./usePolling";
import { useStatus } from "./useStatus";

/** The polled `/api/status`, shared by every part of the home view and the shell. */
export const StatusContext = createContext<Polled<Status> | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const polled = useStatus();
  return <StatusContext.Provider value={polled}>{children}</StatusContext.Provider>;
}

export function useStatusContext(): Polled<Status> {
  const value = useContext(StatusContext);
  if (!value) throw new Error("useStatusContext needs a StatusProvider");
  return value;
}
