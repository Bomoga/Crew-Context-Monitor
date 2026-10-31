import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

export type Domain = "cardio" | "air" | "thermal" | "radiation";

export interface Checkpoint {
  /** Seconds after the scenario start. */
  offset: number;
  cards: Record<
    Domain,
    { level: "green" | "yellow" | "red"; attribution: string | null; crew: string[] }
  >;
  correlation: boolean;
  /** Labels of the simulated events published in the last six hours. */
  sim_events: string[];
  /** Nodes that are offline at this moment. */
  offline: string[];
}

export type Expected = Record<string, { duration: number; checkpoints: Checkpoint[] }>;

/**
 * The states each scenario's `expect:` block says a dashboard should show, read from the YAML
 * through `ccm-sim scenarios expected` (not from the API under test).
 */
export function loadExpected(): Expected {
  const root = resolve(import.meta.dirname, "..", "..");
  const bin = resolve(
    root,
    ".venv",
    existsSync(resolve(root, ".venv", "Scripts")) ? "Scripts" : "bin",
    "ccm-sim",
  );
  const out = execFileSync(bin, ["scenarios", "expected"], {
    encoding: "utf8",
    maxBuffer: 1 << 26,
  });
  return JSON.parse(out) as Expected;
}
