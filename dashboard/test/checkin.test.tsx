import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockApi, polled, renderRoute, status } from "./helpers";

function serve(reply: () => unknown = () => ({ ok: true, event_id: "e-130" })) {
  const calls = mockApi((url, init) => {
    if (url.pathname === "/api/checkin" && init?.method === "POST") return reply();
    return undefined;
  });
  return () => calls.filter((c) => c.url.pathname === "/api/checkin");
}

/** Everything about levels and color on screen, to compare before and after a check-in. */
function levelSnapshot(): string[] {
  const attrs = Array.from(document.querySelectorAll("[data-level], [data-state]")).map(
    (el) =>
      `${el.getAttribute("data-testid") ?? el.tagName}:${el.getAttribute("data-level")}:${el.getAttribute("data-state")}:${el.className}`,
  );
  return [...attrs, document.querySelector("[data-testid=status-bar]")!.textContent ?? ""];
}

describe("daily check-in", () => {
  it("is shown only when a check-in is due", () => {
    serve();
    renderRoute("/", polled(status("all_green"))); // checkin_due is true
    expect(screen.getByRole("dialog", { name: "Daily check-in" })).toBeInTheDocument();
    renderRoute("/", polled(status("air_yellow"))); // checkin_due is false
    expect(screen.getAllByRole("dialog", { name: "Daily check-in" })).toHaveLength(1);
  });

  it("completes in three taps and posts mood, sleep and no note", async () => {
    const posts = serve();
    renderRoute("/", polled(status("all_green")));
    const prompt = screen.getByRole("dialog", { name: "Daily check-in" });
    const send = within(prompt).getByRole("button", { name: "Send check-in" });
    expect(send).toBeDisabled();
    await userEvent.click(within(prompt).getByRole("button", { name: "Mood 4 Good" })); // tap 1
    await userEvent.click(within(prompt).getByRole("button", { name: "Sleep 3 Okay" })); // tap 2
    expect(send).toBeEnabled();
    await userEvent.click(send); // tap 3
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].init?.method).toBe("POST");
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({
      crew: "W1",
      mood: 4,
      sleep: 3,
      note: null,
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Daily check-in" })).toBeNull(),
    );
  });

  it("sends the optional note and the crew member chosen in the strip", async () => {
    const posts = serve();
    renderRoute("/", polled(status("all_green")));
    await userEvent.click(screen.getByRole("button", { name: /W3/ }));
    const prompt = screen.getByRole("dialog", { name: "Daily check-in" });
    expect(prompt).toHaveTextContent("Daily check-in for W3");
    await userEvent.click(within(prompt).getByRole("button", { name: "Add a note" }));
    await userEvent.type(within(prompt).getByLabelText("Note (optional)"), "  Slept badly.  ");
    await userEvent.click(within(prompt).getByRole("button", { name: "Mood 2 Down" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Sleep 1 Poor" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Send check-in" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(String(posts()[0].init?.body))).toEqual({
      crew: "W3",
      mood: 2,
      sleep: 1,
      note: "Slept badly.",
    });
  });

  it("changes no level and no color when it is sent", async () => {
    serve();
    renderRoute("/", polled(status("air_red_cabin", true)));
    const before = levelSnapshot();
    expect(before.length).toBeGreaterThan(5);
    const prompt = screen.getByRole("dialog", { name: "Daily check-in" });
    await userEvent.click(within(prompt).getByRole("button", { name: "Mood 1 Low" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Sleep 1 Poor" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Send check-in" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Daily check-in" })).toBeNull(),
    );
    expect(levelSnapshot()).toEqual(before);
  });

  it("stays open with a message when sending fails", async () => {
    serve(() => new Response('{"detail":"no"}', { status: 500 }));
    renderRoute("/", polled(status("all_green")));
    const prompt = screen.getByRole("dialog", { name: "Daily check-in" });
    await userEvent.click(within(prompt).getByRole("button", { name: "Mood 5 Great" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Sleep 5 Great" }));
    await userEvent.click(within(prompt).getByRole("button", { name: "Send check-in" }));
    expect(await within(prompt).findByRole("alert")).toHaveTextContent("Could not send");
    expect(within(prompt).getByRole("button", { name: "Send check-in" })).toBeEnabled();
  });

  it("can be dismissed with Not now", async () => {
    const posts = serve();
    renderRoute("/", polled(status("all_green")));
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("dialog", { name: "Daily check-in" })).toBeNull();
    expect(posts()).toHaveLength(0);
  });
});
