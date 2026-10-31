import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Events, History } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const prv = fixture<History>("history.prv_6h");
const events = fixture<Events>("events.mixed");

function co2History(): History {
  return {
    metric: "co2_mmhg",
    unit: "mmHg",
    crew: null,
    points: prv.points.map((p, i) => ({
      t: p.t,
      mean: 0.6 + i * 0.4,
      min: 0.5 + i * 0.4,
      max: 0.7 + i * 0.4,
    })),
    baseline: null,
    cusum: null,
    limits: { yellow: 2.5, red: 3.0 },
  };
}

function hrResid(): History {
  return {
    ...prv,
    metric: "hr_resid",
    unit: "bpm",
    points: prv.points.map((p) => ({ ...p, mean: 1, min: 0, max: 2 })),
  };
}

function api(extraEvents: Events["events"] = []) {
  return mockApi((url) => {
    if (url.pathname === "/api/history") {
      const metric = url.searchParams.get("metric");
      return metric === "co2_mmhg" ? co2History() : metric === "hr_resid" ? hrResid() : prv;
    }
    if (url.pathname === "/api/events") return { events: [...events.events, ...extraEvents] };
    return undefined;
  });
}

async function timeline() {
  const chart = await screen.findByTestId("timeline-chart");
  await waitFor(() => expect(chart.querySelector(".series-co2")).not.toBeNull());
  return chart;
}

describe("fused timeline", () => {
  it("draws CO2 and pulse-rate variability for the selected crew member over six hours", async () => {
    const calls = api();
    renderRoute("/", polled(status("all_green")));
    const chart = await timeline();
    expect(chart.querySelector(".series-crew")).not.toBeNull();
    const urls = calls.map((c) => c.url.search);
    expect(urls).toContain("?metric=co2_mmhg&hours=6&step=60");
    expect(urls).toContain("?metric=prv&crew=W1&hours=6&step=60");
    expect(screen.getByRole("heading", { name: /pulse-rate variability/i })).toHaveTextContent(
      "W1",
    );
    expect(chart).toHaveAttribute("aria-label", expect.stringContaining("pulse-rate variability"));
  });

  it("has one marker per event in range, with simulated events drawn differently", async () => {
    api([{ ...events.events[0], id: "e-old", t: events.events[0].t - 8 * 3600 }]); // out of range
    renderRoute("/", polled(status("all_green")));
    const chart = await timeline();
    const markers = chart.querySelectorAll(".event-marker");
    expect(markers).toHaveLength(events.events.length);
    const simulated = events.events.filter((e) => e.simulated).length;
    expect(chart.querySelectorAll(".event-marker.simulated")).toHaveLength(simulated);
    expect(chart.querySelectorAll(".event-marker.observed")).toHaveLength(
      events.events.length - simulated,
    );
    expect(screen.getByText(/dashed lines mark simulated events/i)).toBeInTheDocument();
  });

  it("shows the correlation lag label and band when the status has a correlation", async () => {
    api();
    const s = status("correlation_active");
    renderRoute("/", polled(s));
    const chart = await timeline();
    expect(screen.getByTestId("lag-label")).toHaveTextContent(s.correlation!.sentence);
    expect(chart.querySelector(".lag-band")).not.toBeNull();
    expect(chart.querySelectorAll(".event-marker.simulated").length).toBeGreaterThan(0);
  });

  it("has no lag label or band without a correlation", async () => {
    api();
    renderRoute("/", polled(status("all_green")));
    const chart = await timeline();
    expect(screen.getByTestId("lag-label")).toBeEmptyDOMElement();
    expect(chart.querySelector(".lag-band")).toBeNull();
  });

  it("switches to the HR residual and back", async () => {
    const calls = api();
    renderRoute("/", polled(status("all_green")));
    await timeline();
    const group = screen.getByRole("group", { name: "Series" });
    expect(within(group).getByRole("button", { name: "Pulse-rate variability" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(within(group).getByRole("button", { name: "HR residual" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.search.includes("metric=hr_resid&crew=W1"))).toBe(true),
    );
    expect(within(group).getByRole("button", { name: "HR residual" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("heading", { name: /hr residual/i })).toBeInTheDocument();
    expect(screen.getByTestId("timeline-chart")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("hr residual in bpm"),
    );
    await userEvent.click(within(group).getByRole("button", { name: "Pulse-rate variability" }));
    expect(screen.getByRole("heading", { name: /pulse-rate variability/i })).toBeInTheDocument();
  });

  it("follows the crew strip selection", async () => {
    const calls = api();
    renderRoute("/", polled(status("all_green")));
    await timeline();
    await userEvent.click(screen.getByRole("button", { name: /W3/ }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.search.includes("metric=prv&crew=W3"))).toBe(true),
    );
  });
});
