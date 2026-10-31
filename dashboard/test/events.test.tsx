import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Events } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const mixed = fixture<Events>("events.mixed");

function serve(body: Events = mixed) {
  return mockApi((url) => (url.pathname === "/api/events" ? body : undefined));
}

function log() {
  return screen.getByRole("region", { name: "Event log" });
}

async function rows() {
  const region = await screen.findByRole("region", { name: "Event log" });
  await within(region).findAllByRole("listitem");
  return within(region).getAllByRole("listitem");
}

describe("events view", () => {
  it("lists every event, newest first", async () => {
    serve();
    renderRoute("/events", polled(status("all_green")));
    const items = await rows();
    expect(items).toHaveLength(mixed.events.length);
    const times = items.map((li) => li.querySelector("time")!.getAttribute("datetime")!);
    expect(times).toEqual([...times].sort().reverse());
    expect(items[0]).toHaveAttribute("data-testid", "event-e-125"); // the latest in the fixture
    expect(items.at(-1)).toHaveAttribute("data-testid", "event-e-120");
  });

  it("puts a Simulated badge on simulator events only", async () => {
    serve();
    renderRoute("/events", polled(status("all_green")));
    await rows();
    const simulated = mixed.events.filter((e) => e.simulated).map((e) => e.id);
    expect(simulated).toEqual(["e-120"]);
    expect(screen.getByTestId("simulated-e-120")).toHaveTextContent("Simulated");
    expect(screen.queryByTestId("simulated-e-121")).toBeNull();
    expect(screen.getAllByText("Simulated", { selector: "span" })).toHaveLength(1);
  });

  it("shows check-ins as context", async () => {
    serve();
    renderRoute("/events", polled(status("all_green")));
    const items = await rows();
    const checkin = items.find((li) => li.getAttribute("data-kind") === "checkin")!;
    expect(checkin).toHaveTextContent("Check-in (context)");
    expect(checkin).toHaveTextContent("mood 4 of 5, sleep 3 of 5");
    expect(checkin).toHaveClass("text-muted");
  });

  it("filters by kind and can show everything again", async () => {
    serve();
    renderRoute("/events", polled(status("all_green")));
    await rows();
    const group = screen.getByRole("group", { name: "Show" });
    await userEvent.click(within(group).getByRole("button", { name: "Check-ins" }));
    let items = within(log()).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveAttribute("data-kind", "checkin");
    await userEvent.click(within(group).getByRole("button", { name: "Simulated events" }));
    items = within(log()).getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-kind"))).toEqual(["sim_event"]);
    await userEvent.click(within(group).getByRole("button", { name: "Drifts" }));
    expect(log()).toHaveTextContent("Pulse-rate variability 36 ms");
    await userEvent.click(within(group).getByRole("button", { name: "All" }));
    await waitFor(() =>
      expect(within(log()).getAllByRole("listitem")).toHaveLength(mixed.events.length),
    );
  });

  it("says so when there are no events", async () => {
    serve({ events: [] });
    renderRoute("/events", polled(status("all_green")));
    expect(await screen.findByText("No events to show.")).toBeInTheDocument();
  });
});
