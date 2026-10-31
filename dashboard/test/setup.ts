import "@testing-library/jest-dom/vitest";
import { cloneElement, type ReactElement } from "react";
import { afterEach, beforeEach, vi } from "vitest";

// jsdom has no layout, so Recharts' ResponsiveContainer would render nothing. Give charts a size.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: ReactElement<{ width?: number; height?: number }>;
    }) => cloneElement(children, { width: 900, height: 320 }),
  };
});

// No test reaches a real network; individual tests replace this with their own responses.
beforeEach(() => {
  vi.stubGlobal("fetch", () => Promise.reject(new TypeError("no network in tests")));
});

afterEach(() => {
  vi.unstubAllGlobals();
});
