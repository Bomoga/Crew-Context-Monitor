import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { polled, renderRoute, status } from "./helpers";

const STATES = ["all_green", "air_yellow", "air_red_cabin", "learning"] as const;

describe("status bar", () => {
  it.each(STATES)("shows the %s fixture's sentence, level word and action", (name) => {
    const s = status(name);
    renderRoute("/", polled(s));
    const bar = screen.getByTestId("status-bar");
    expect(bar).toHaveTextContent(s.crew_status.sentence);
    const word = { green: "Green", yellow: "Yellow", red: "Red" }[s.crew_status.level];
    expect(within(bar).getByText(word)).toBeInTheDocument();
    if (s.crew_status.action) expect(bar).toHaveTextContent(s.crew_status.action);
  });

  it("has an identical frame in every state, so nothing moves between them", () => {
    const frames = STATES.map((name) => {
      const { unmount } = renderRoute("/", polled(status(name)));
      const bar = screen.getByTestId("status-bar");
      const frame = { tag: bar.tagName, className: bar.className };
      unmount();
      return frame;
    });
    for (const frame of frames) expect(frame).toEqual(frames[0]);
    expect(frames[0].className).toMatch(/\bh-24\b/); // a fixed height, not content-sized
  });

  it("shows the time until alerts start while learning", () => {
    const s = status("learning");
    renderRoute("/", polled(s));
    const bar = screen.getByTestId("status-bar");
    expect(bar).toHaveAttribute("data-state", "learning");
    expect(bar).toHaveTextContent("Alerts start in 3 h 20 min");
  });

  it("shows the domain and attribution of the worst card", () => {
    renderRoute("/", polled(status("air_red_cabin")));
    const bar = screen.getByTestId("status-bar");
    expect(bar).toHaveTextContent("Air quality");
    expect(bar).toHaveTextContent("Attribution: Cabin");
    expect(bar).toHaveTextContent("Next step: Check scrubber, increase ventilation");
  });

  it("has a placeholder of the same frame before the first reading", () => {
    const { unmount } = renderRoute("/", polled(status("all_green")));
    const full = screen.getByTestId("status-bar").className;
    unmount();
    renderRoute("/", polled(null));
    expect(screen.getByTestId("status-bar").className).toBe(full);
  });
});

describe("crew strip", () => {
  it("has one chip per crew member with level, online state and the source word", () => {
    renderRoute("/", polled(status("all_green")));
    const strip = screen.getByTestId("crew-strip");
    expect(within(strip).getAllByRole("button")).toHaveLength(3);
    expect(screen.getByTestId("source-W1")).toHaveTextContent("Hardware");
    expect(screen.getByTestId("source-W2")).toHaveTextContent("Simulator");
    expect(screen.getByTestId("source-W3")).toHaveTextContent("Simulator");
    expect(within(strip).getAllByText("Online")).toHaveLength(3);
    expect(within(strip).getAllByText("Green")).toHaveLength(3);
  });

  it.each(STATES)("shows Hardware or Simulator on every chip in %s", (name) => {
    renderRoute("/", polled(status(name)));
    for (const c of status(name).crew) {
      expect(screen.getByTestId(`source-${c.id}`).textContent).toMatch(/^(Hardware|Simulator)$/);
    }
  });

  it("shows each crew member's level and offline state", () => {
    renderRoute("/", polled(status("cardio_yellow_individual")));
    const strip = screen.getByTestId("crew-strip");
    expect(within(strip).getByRole("button", { name: /W2/ })).toHaveTextContent("Yellow");
    expect(within(strip).getByRole("button", { name: /W1/ })).toHaveTextContent("Green");
    renderRoute("/", polled(status("node_offline")));
    expect(screen.getAllByText("Offline").length).toBeGreaterThan(0);
  });

  it("selects the crew member for the timeline when a chip is clicked", async () => {
    renderRoute("/", polled(status("all_green")));
    const w1 = screen.getByRole("button", { name: /W1/ });
    const w3 = screen.getByRole("button", { name: /W3/ });
    expect(w1).toHaveAttribute("aria-pressed", "true"); // the first is selected by default
    await userEvent.click(w3);
    expect(w3).toHaveAttribute("aria-pressed", "true");
    expect(w1).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the chip frame identical across levels", () => {
    const frames = ["all_green", "air_red_cabin"].map((name) => {
      const { unmount } = renderRoute("/", polled(status(name)));
      const classes = within(screen.getByTestId("crew-strip"))
        .getAllByRole("button")
        .map((b) => b.className.replace(/border-accent|ring-2|ring-accent|border-line/g, ""));
      unmount();
      return classes;
    });
    expect(frames[0]).toEqual(frames[1]);
  });
});
