import { defineConfig, devices } from "@playwright/test";

// e2e runs against the production build served by the mock API (make serve-mock) on :8000.
export default defineConfig({
  testDir: "e2e",
  reporter: [["list"]],
  outputDir: "test-results",
  use: { baseURL: process.env.CCM_BASE_URL ?? "http://127.0.0.1:8000", trace: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
