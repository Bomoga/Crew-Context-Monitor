import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

// e2e runs against the production build (dashboard/dist) served by the mock API, with no Vite
// process. Build first (`make e2e` does). Override CCM_BASE_URL to test an already running server.
const port = Number(process.env.CCM_E2E_PORT ?? 8000);
const scenario = process.env.CCM_E2E_SCENARIO ?? "scrubber_failure";
const speed = process.env.CCM_E2E_SPEED ?? "60";
const fastForward = process.env.CCM_E2E_FAST_FORWARD ?? "13200"; // 3 h 40 min of the scenario

const root = resolve(import.meta.dirname, "..");
const venvBin = resolve(
  root,
  ".venv",
  existsSync(resolve(root, ".venv", "Scripts")) ? "Scripts" : "bin",
);
const ccmSim = resolve(venvBin, "ccm-sim");
const baseURL = process.env.CCM_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "e2e",
  reporter: [["list"]],
  outputDir: "test-results",
  timeout: 60_000,
  workers: 1, // one mock API is shared by every test
  use: { baseURL, trace: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.CCM_BASE_URL
    ? undefined
    : {
        command: `"${ccmSim}" serve-mock --scenario ${scenario} --speed ${speed} --port ${port} --fast-forward ${fastForward}`,
        url: `${baseURL}/api/status`,
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
