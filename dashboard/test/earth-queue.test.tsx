import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { EarthQueue, EarthQueueItem } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const queue = fixture<EarthQueue>("earth_queue.pending");

/** Serve the queue; `approve` decides what a POST gets back. */
function serve(approve: (id: string) => unknown) {
  return mockApi((url, init) => {
    if (url.pathname === "/api/earth-queue" && init?.method !== "POST") return queue;
    if (url.pathname.startsWith("/api/earth-queue/") && init?.method === "POST") {
      return approve(url.pathname.split("/")[3]);
    }
    return undefined;
  });
}

async function panel() {
  const el = await screen.findByRole("region", { name: "Earth queue" });
  await within(el).findByTestId("queue-q-2");
  return el;
}

describe("Earth queue panel", () => {
  it("lists each item with tier, size, approval state and a payload preview", async () => {
    serve(() => undefined);
    renderRoute("/", polled(status("all_green")));
    const el = await panel();
    const row = within(el).getByTestId("queue-q-2");
    expect(row).toHaveTextContent("Flight surgeon");
    expect(row).toHaveTextContent("318 bytes");
    expect(within(row).getByTestId("queue-state-q-2")).toHaveTextContent("Waiting for approval");
    expect(row).toHaveTextContent(queue.items[1].summary);
    expect(within(row).getByText("What would be sent")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Approve" })).toBeEnabled();
    const done = within(el).getByTestId("queue-q-1");
    expect(within(done).getByTestId("queue-state-q-1")).toHaveTextContent("Approved");
    expect(within(done).getByRole("button", { name: "Approved" })).toBeDisabled();
  });

  it("shows pending items first", async () => {
    serve(() => undefined);
    renderRoute("/", polled(status("all_green")));
    const el = await panel();
    const ids = within(el)
      .getAllByRole("listitem")
      .map((li) => li.getAttribute("data-testid"));
    expect(ids.slice(-1)).toEqual(["queue-q-1"]);
  });

  it("counts down to the next window from the API time", async () => {
    serve(() => undefined);
    const s = status("all_green");
    renderRoute("/", polled(s));
    await panel();
    const minutes = Math.round((queue.next_window_t - s.t) / 60);
    expect(screen.getByTestId("window-countdown")).toHaveTextContent(
      `Next comms window in ${minutes} min`,
    );
  });

  it("approves once, shows it approved, and stays approved", async () => {
    let posts = 0;
    const calls = serve((id) => {
      posts += 1;
      return { ...queue.items.find((i) => i.id === id)!, approved: true };
    });
    renderRoute("/", polled(status("all_green")));
    const el = await panel();
    await userEvent.click(within(el).getAllByRole("button", { name: "Approve" })[0]);
    await waitFor(() => expect(posts).toBe(1));
    const posted = calls.filter((c) => c.init?.method === "POST");
    expect(posted).toHaveLength(1);
    expect(posted[0].url.pathname).toBe("/api/earth-queue/q-2/approve");
    expect(within(el).getByTestId("queue-state-q-2")).toHaveTextContent(/^Approved/);
    expect(within(el).queryByRole("alert")).toBeNull();
  });

  it("shows the item approved at once and rolls back when the server fails", async () => {
    let fail: (r: Response) => void = () => {};
    serve(() => new Promise<Response>((resolve) => (fail = resolve)));
    renderRoute("/", polled(status("all_green")));
    const el = await panel();
    await userEvent.click(within(el).getAllByRole("button", { name: "Approve" })[0]);
    // optimistic: approved before the server has answered
    expect(within(el).getByTestId("queue-state-q-2")).toHaveTextContent(/^Approved/);
    expect(within(el).queryByRole("alert")).toBeNull();
    fail(new Response('{"detail":"boom"}', { status: 500 }));
    await waitFor(() => expect(within(el).getByRole("alert")).toBeInTheDocument());
    expect(within(el).getByTestId("queue-state-q-2")).toHaveTextContent("Waiting for approval");
    expect(within(el).getAllByRole("button", { name: "Approve" })[0]).toBeEnabled();
    expect(within(el).getByRole("alert")).toHaveTextContent("q-2");
  });

  it("says so when the queue is empty", async () => {
    mockApi((url) =>
      url.pathname === "/api/earth-queue"
        ? { next_window_t: 1, items: [] as EarthQueueItem[] }
        : undefined,
    );
    renderRoute("/", polled(status("all_green")));
    expect(await screen.findByText("Nothing is waiting for Earth.")).toBeInTheDocument();
  });
});
